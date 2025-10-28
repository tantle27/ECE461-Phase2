import asyncio
import json
import logging
import os
import re
import ssl
from copy import deepcopy
from typing import Any, Dict

import aiohttp


class GenAIClient:
    def __init__(self):
        self.url = "https://genai.rcac.purdue.edu/api/chat/completions"
        env_api_key = os.environ.get("GENAI_API_KEY")
        self.has_api_key = bool(env_api_key)
        self.max_retries = 3
        self.retry_delay_seconds = 0.5
        self._default_chat_response = (
            "No performance claims found in the documentation."
        )
        self._default_performance_result: Dict[str, Any] = {
            "mentions_benchmarks": 0.0,
            "has_metrics": 0.0,
            "claims": [],
            "score": 0.0,
        }
        self._default_clarity_score = 0.5
        if env_api_key:
            self.headers = {
                "Authorization": f"Bearer {env_api_key}",
                "Content-Type": "application/json"
            }
        else:
            self.headers = {
                "Content-Type": "application/json"
            }

    async def chat(self, message: str, model: str = "llama3.3:70b") -> str:
        # If no API key is available, return a default response
        if not self.has_api_key:
            return self._default_chat_response

        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ]
        }
        # Create SSL context that doesn't verify certificates for servers
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with aiohttp.ClientSession(
                    connector=connector
                ) as session:
                    async with session.post(
                        self.url, headers=self.headers, json=body
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data['choices'][0]['message']['content']
                        if response.status == 401:
                            logging.error(
                                "GenAI authentication failed. "
                                "Falling back to default response."
                            )
                            self.has_api_key = False
                            return self._default_chat_response
                        if 500 <= response.status < 600:
                            error_text = await response.text()
                            logging.warning(
                                "GenAI service error (%s): %s", response.status,
                                error_text.strip()
                            )
                            last_error = Exception(
                                f"Error: {response.status}, {error_text}"
                            )
                            await asyncio.sleep(
                                self.retry_delay_seconds * attempt
                            )
                            continue
                        error = await response.text()
                        raise Exception(f"Error: {response.status}, {error}")
            except aiohttp.ClientError as exc:
                logging.warning(
                    "GenAI client error on attempt %d/%d: %s",
                    attempt,
                    self.max_retries,
                    str(exc)
                )
                last_error = exc
                await asyncio.sleep(self.retry_delay_seconds * attempt)

        if last_error:
            raise Exception("GenAI chat failed after retries") from last_error
        raise Exception("GenAI chat failed without specific error")

    async def get_performance_claims(self, readme_text: str) -> dict:
        # If no API key is available, return a default score
        if not self.has_api_key:
            return deepcopy(self._default_performance_result)

        try:
            extraction_prompt = (
                self._read_prompt(
                    "src/api/performance_claims_extraction_prompt.txt"
                ) + readme_text
            )
            extraction_response = await self.chat(extraction_prompt)

            conversion_prompt = (
                self._read_prompt(
                    "src/api/performance_claims_conversion_prompt.txt"
                ) + "\n" + extraction_response
            )
            json_response = await self.chat(conversion_prompt)
        except Exception as exc:
            logging.warning(
                "Falling back to default performance claims due to GenAI "
                "error: %s",
                str(exc)
            )
            return deepcopy(self._default_performance_result)

        # Extract JSON object from response (handles markdown code blocks)
        match = re.search(r'\{[^}]*\}', json_response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                logging.warning(
                    "Failed to parse extracted JSON. Returning defaults."
                )
                return deepcopy(self._default_performance_result)

        # Try parsing the entire response as fallback
        try:
            return json.loads(json_response)
        except json.JSONDecodeError:
            logging.warning(
                "Failed to parse GenAI response as JSON. Returning defaults."
            )
            return deepcopy(self._default_performance_result)

    async def get_readme_clarity(self, readme_text: str) -> float:
        # If no API key is available, return a default score
        if not self.has_api_key:
            return self._default_clarity_score  # Neutral score when API is unavailable

        prompt = self._read_prompt("src/api/readme_clarity_ai_prompt.txt")
        prompt += readme_text
        try:
            response = await self.chat(prompt)
        except Exception as exc:
            logging.warning(
                "Falling back to default clarity score due to GenAI error: %s",
                str(exc)
            )
            return self._default_clarity_score

        # Try to extract a floating point number from the response
        # Handle various possible formats from LLM

        # First, try to parse the response directly as a float
        try:
            return float(response.strip())
        except ValueError:
            pass

        # Try to find a number in the response using regex
        # Look for patterns like "0.6", "0.85", "1.0", etc.
        number_match = re.search(r'\b(?:0?\.\d+|1\.0+|0\.0+|1)\b', response)
        if number_match:
            try:
                value = float(number_match.group(0))
                # Ensure the value is within expected range [0, 1]
                return max(0.0, min(1.0, value))
            except ValueError:
                pass

        # Try to find any decimal number in the response
        decimal_match = re.search(r'\d*\.?\d+', response)
        if decimal_match:
            try:
                value = float(decimal_match.group(0))
                # Ensure the value is within expected range [0, 1]
                return max(0.0, min(1.0, value))
            except ValueError:
                pass

        # If all parsing attempts fail,
        # return a default score based on content length
        # This is a fallback to prevent complete failure
        logging.warning(
            f"Could not parse GenAI response as float: {response[:200]}..."
            )

        # If we can't parse any number, raise an exception
        logging.warning(
            f"Could not parse GenAI response as float: {response[:200]}..."
            )
        return self._default_clarity_score

    @staticmethod
    def _read_prompt(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            logging.error("Prompt file not found: %s", path)
        except OSError as exc:
            logging.error("Failed to read prompt %s: %s", path, str(exc))
        return ""


if __name__ == "__main__":
    import asyncio

    async def main():
        client = GenAIClient()
        readme_text = (
            "This is a sample README file for a machine learning model. "
            "It includes performance metrics such as accuracy and F1-score. "
            "The model achieves 92% accuracy on the test set and has been "
            "benchmarked against several baselines."
        )
        performance_claims = await client.get_performance_claims(readme_text)

        print("Performance Claims:", performance_claims)

        clarity_score = await client.get_readme_clarity(readme_text)
        print("Readme Clarity Score:", clarity_score)

    asyncio.run(main())
