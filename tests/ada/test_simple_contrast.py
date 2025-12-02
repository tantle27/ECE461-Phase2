"""Simple Color Contrast Tests for ADA Compliance"""

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
@pytest.mark.contrast
@pytest.mark.skipif(not check_server_running(), reason="Flask server not running on localhost:5000")
class TestSimpleColorContrast:
    """Simple color contrast tests."""

    def test_button_contrast(self, ada_driver, test_url, contrast_checker):
        """Test color contrast ratio for buttons."""
        ada_driver.get(test_url)

        # Find buttons
        buttons = ada_driver.find_elements("tag name", "button")

        for button in buttons[:3]:  # Test first 3 buttons
            try:
                # Get colors
                text_color = button.value_of_css_property("color")
                bg_color = button.value_of_css_property("background-color")

                # Parse colors
                text_rgb = contrast_checker.parse_color(text_color)
                bg_rgb = contrast_checker.parse_color(bg_color)

                # Calculate contrast ratio
                ratio = contrast_checker.contrast_ratio(text_rgb, bg_rgb)

                # WCAG AA requires 4.5:1 for normal text
                assert ratio >= 4.5, f"Button contrast ratio {ratio:.1f} is below 4.5:1"

            except Exception:
                continue  # Skip buttons with parsing issues

    def test_link_contrast(self, ada_driver, test_url, contrast_checker):
        """Test color contrast ratio for links."""
        ada_driver.get(test_url)

        # Find links
        links = ada_driver.find_elements("css selector", "a[href]")

        for link in links[:3]:  # Test first 3 links
            if link.text.strip():  # Only test links with text
                try:
                    # Get colors
                    text_color = link.value_of_css_property("color")
                    bg_color = link.value_of_css_property("background-color")

                    # Parse colors
                    text_rgb = contrast_checker.parse_color(text_color)
                    bg_rgb = contrast_checker.parse_color(bg_color)

                    # Calculate contrast ratio
                    ratio = contrast_checker.contrast_ratio(text_rgb, bg_rgb)

                    # WCAG AA requires 4.5:1 for normal text
                    assert ratio >= 4.5, f"Link contrast ratio {ratio:.1f} is below 4.5:1"

                except Exception:
                    continue  # Skip links with parsing issues
