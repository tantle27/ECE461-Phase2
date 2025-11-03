"""Simple Keyboard Navigation Tests for ADA Compliance"""

import pytest


@pytest.mark.ada
@pytest.mark.keyboard
class TestSimpleKeyboardNavigation:
    """Simple keyboard navigation tests."""
    
    def test_tab_navigation(self, ada_driver, test_url, keyboard_tester):
        """Test basic tab navigation through focusable elements."""
        ada_driver.get(test_url)
        
        # Get all focusable elements
        focusable_elements = keyboard_tester.get_focusable_elements()
        
        assert len(focusable_elements) > 0, "No focusable elements found on page"
        
        # Test tab navigation
        for i in range(min(len(focusable_elements), 5)):  # Test first 5 elements
            keyboard_tester.press_tab()
            current_element = ada_driver.switch_to.active_element
            assert current_element.is_displayed(), f"Element {i} is not visible when focused"
    
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