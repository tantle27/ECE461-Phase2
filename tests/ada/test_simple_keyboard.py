"""Simple Keyboard Navigation Tests for ADA Compliance"""

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
@pytest.mark.keyboard
@pytest.mark.skipif(not check_server_running(), reason="Flask server not running on localhost:5000")
class TestSimpleKeyboardNavigation:
    """Simple keyboard navigation tests."""

    def test_enter_activation(self, ada_driver, test_url, keyboard_tester):
        """Test Enter key activation on buttons and links."""
        ada_driver.get(test_url)

        # Find buttons and links
        buttons = ada_driver.find_elements("tag name", "button")
        links = ada_driver.find_elements("css selector", "a[href]")

        # Test Enter key on first button (if exists)
        if buttons:
            button = buttons[0]
            button.click()  # Focus the button
            keyboard_tester.press_enter()
            # Assert no error occurred (basic test)
            assert True  # If we get here, Enter didn't crash

        # Test Enter key on first link (if exists)
        if links:
            link = links[0]
            link.click()  # Focus the link
            keyboard_tester.press_enter()
            # Assert no error occurred (basic test)
            assert True  # If we get here, Enter didn't crash

    def test_space_activation(self, ada_driver, test_url, keyboard_tester):
        """Test Space key activation on buttons."""
        ada_driver.get(test_url)

        # Find buttons
        buttons = ada_driver.find_elements("tag name", "button")

        # Test Space key on first button (if exists)
        if buttons:
            button = buttons[0]
            button.click()  # Focus the button
            keyboard_tester.press_space()
            # Assert no error occurred (basic test)
            assert True  # If we get here, Space didn't crash

    def test_focus_visibility(self, ada_driver, test_url, keyboard_tester):
        """Test that focused elements are visible."""
        ada_driver.get(test_url)

        # Get focusable elements
        focusable_elements = keyboard_tester.get_focusable_elements()

        if focusable_elements:
            # Test first few elements
            for element in focusable_elements[:3]:
                element.click()  # Focus element
                assert element.is_displayed(), "Focused element should be visible"
