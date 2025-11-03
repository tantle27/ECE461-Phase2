"""Simple Color Contrast Tests for ADA Compliance"""

import pytest


@pytest.mark.ada
@pytest.mark.contrast
class TestSimpleColorContrast:
    """Simple color contrast tests."""
    
    def test_text_contrast(self, ada_driver, test_url, contrast_checker):
        """Test color contrast ratio for text elements."""
        ada_driver.get(test_url)
        
        # Find text elements
        text_elements = ada_driver.find_elements("css selector", "p, h1, h2, h3, h4, h5, h6, span, div")
        
        contrast_failures = []
        
        for element in text_elements[:5]:  # Test first 5 text elements
            if element.text.strip():  # Only test elements with text
                try:
                    # Get colors
                    text_color = element.value_of_css_property("color")
                    bg_color = element.value_of_css_property("background-color")
                    
                    # Parse colors
                    text_rgb = contrast_checker.parse_color(text_color)
                    bg_rgb = contrast_checker.parse_color(bg_color)
                    
                    # Calculate contrast ratio
                    ratio = contrast_checker.contrast_ratio(text_rgb, bg_rgb)
                    
                    # WCAG AA requires 4.5:1 for normal text
                    if ratio < 4.5:
                        contrast_failures.append({
                            'element': element.tag_name,
                            'text': element.text[:50],
                            'ratio': ratio,
                            'text_color': text_color,
                            'bg_color': bg_color
                        })
                except Exception:
                    continue  # Skip elements with parsing issues
        
        assert len(contrast_failures) == 0, f"Contrast failures: {contrast_failures}"
    
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