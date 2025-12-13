import asyncio
import json
import os
import re

import boto3


class BedrockClient:
    """Minimal async wrapper around AWS Bedrock invoke_model that matches the
    async interface used by GenAIClient in this repo:
      - async chat(message: str, model: str | None) -> str
      - async get_performance_claims(readme_text: str) -> dict
      - async get_readme_clarity(readme_text: str) -> float

    This implementation delegates synchronous boto3 calls into a threadpool
    so callers can await the methods.
    """

    def __init__(self, model_id: str | None = None, region: str | None = None):
        self.model_id = model_id or os.environ.get("BEDROCK_MODEL_ID")
        self.region = region or os.environ.get("AWS_REGION")
        # service name used in boto3 for Bedrock runtime
        self._client = boto3.client("bedrock-runtime", region_name=self.region)

    def _invoke_sync(self, model_id: str, payload_bytes: bytes) -> str:
        # Use InvokeModel API
        resp = self._client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=payload_bytes,
        )
        body_stream = resp.get("body")
        if body_stream is None:
            raise RuntimeError("No body in Bedrock response")
        # body_stream is a botocore.response.StreamingBody
        raw = body_stream.read()
        try:
            return raw.decode("utf-8")
        except Exception:
            return str(raw)

    async def chat(self, message: str, model: str | None = None) -> str:
        model_id = model or self.model_id
        if not model_id:
            raise ValueError("No Bedrock model id configured (BEDROCK_MODEL_ID)")
        payload = json.dumps({"input": message})
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._invoke_sync, model_id, payload.encode("utf-8")
        )

    async def get_performance_claims(self, readme_text: str) -> dict:
        prompt = "Extract performance claims as JSON from the following README:\n\n" + readme_text
        try:
            resp = await self.chat(prompt)
            m = re.search(r"\{.*\}", resp, flags=re.DOTALL)
            if m:
                return json.loads(m.group(0))
            return json.loads(resp)
        except Exception:
            # Return compatible default structure used by GenAIClient
            return {"mentions_benchmarks": 0.0, "has_metrics": 0.0, "claims": [], "score": 0.0}

    async def get_readme_clarity(self, readme_text: str) -> float:
        prompt = "Score the clarity of the following README between 0 and 1:\n\n" + readme_text
        try:
            resp = await self.chat(prompt)
            try:
                return float(resp.strip())
            except Exception:
                m = re.search(r"\b(?:0?\.\d+|1(?:\.0+)?)\b", resp)
                if m:
                    return float(m.group(0))
        except Exception:
            pass
        return 0.5
