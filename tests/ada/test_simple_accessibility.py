"""Simple General Accessibility Tests for ADA Compliance"""

import pytest
import requests


def check_server_running(url="http://localhost:5000"):
    """Check if the Flask server is running."""
    try:
        response = requests.get(f"{url}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


@pytest.mark.ada
@pytest.mark.accessibility
@pytest.mark.skipif(not check_server_running(), reason="Flask server not running on localhost:5000")
class TestSimpleAccessibility:
    """Simple general accessibility tests."""

    def test_images_have_alt_text(self, ada_driver, test_url):
        """Test that images have alt text."""
        ada_driver.get(test_url)

        # Find all images
        images = ada_driver.find_elements("tag name", "img")

        missing_alt = []
        for img in images:
            alt_text = img.get_attribute("alt")
            src = img.get_attribute("src")

            if alt_text is None or alt_text.strip() == "":
                missing_alt.append(src or "unknown source")

        assert len(missing_alt) == 0, f"Images missing alt text: {missing_alt}"

    def test_form_inputs_have_labels(self, ada_driver, test_url):
        """Test that form inputs have associated labels."""
        ada_driver.get(test_url)

        # Find form inputs
        inputs = ada_driver.find_elements("css selector", "input, select, textarea")

        unlabeled_inputs = []
        for input_elem in inputs:
            input_id = input_elem.get_attribute("id")
            input_type = input_elem.get_attribute("type")

            # Skip hidden inputs and buttons
            if input_type in ["hidden", "submit", "button"]:
                continue

            # Check for label
            has_label = False

            # Check for label with 'for' attribute
            if input_id:
                labels = ada_driver.find_elements("css selector", f"label[for='{input_id}']")
                if labels:
                    has_label = True

            # Check for aria-label
            if not has_label:
                aria_label = input_elem.get_attribute("aria-label")
                if aria_label and aria_label.strip():
                    has_label = True

            # Check for placeholder (basic fallback)
            if not has_label:
                placeholder = input_elem.get_attribute("placeholder")
                if placeholder and placeholder.strip():
                    has_label = True

            if not has_label:
                unlabeled_inputs.append({"id": input_id, "type": input_type, "name": input_elem.get_attribute("name")})

        assert len(unlabeled_inputs) == 0, f"Unlabeled inputs: {unlabeled_inputs}"

    def test_headings_structure(self, ada_driver, test_url):
        """Test that headings follow a logical structure."""
        ada_driver.get(test_url)

        # Find all headings
        headings = []
        for level in range(1, 7):  # h1 to h6
            heading_elements = ada_driver.find_elements("tag name", f"h{level}")
            for heading in heading_elements:
                headings.append({"level": level, "text": heading.text.strip()[:50], "element": heading})

        if not headings:
            pytest.skip("No headings found on page")

        # Sort by document order (approximate)
        # Basic check: ensure we have at least one h1
        h1_count = len([h for h in headings if h["level"] == 1])
        assert h1_count >= 1, "Page should have at least one h1 heading"

    def test_buttons_have_accessible_names(self, ada_driver, test_url):
        """Test that buttons have accessible names."""
        ada_driver.get(test_url)

        # Find all buttons
        buttons = ada_driver.find_elements("tag name", "button")
        button_inputs = ada_driver.find_elements("css selector", "input[type='button'], input[type='submit']")

        all_buttons = buttons + button_inputs
        unnamed_buttons = []

        for button in all_buttons:
            has_name = False

            # Check button text
            if button.text.strip():
                has_name = True

            # Check aria-label
            if not has_name:
                aria_label = button.get_attribute("aria-label")
                if aria_label and aria_label.strip():
                    has_name = True

            # Check value attribute (for input buttons)
            if not has_name:
                value = button.get_attribute("value")
                if value and value.strip():
                    has_name = True

            if not has_name:
                unnamed_buttons.append(
                    {
                        "id": button.get_attribute("id"),
                        "class": button.get_attribute("class"),
                        "type": button.get_attribute("type"),
                    }
                )

        assert len(unnamed_buttons) == 0, f"Buttons without accessible names: {unnamed_buttons}"

    def test_links_have_meaningful_text(self, ada_driver, test_url):
        """Test that links have meaningful text."""
        ada_driver.get(test_url)

        # Find all links
        links = ada_driver.find_elements("css selector", "a[href]")

        problematic_links = []
        generic_text = ["click here", "read more", "more", "here", "link"]

        for link in links:
            link_text = link.text.strip().lower()
            aria_label = link.get_attribute("aria-label")

            # Check if link has meaningful text
            if not link_text and not aria_label:
                problematic_links.append("Empty link text")
            elif link_text in generic_text:
                problematic_links.append(f"Generic link text: {link_text}")

        assert len(problematic_links) == 0, f"Links with poor text: {problematic_links}"
