"""Simple ADA Testing Utilities for Selenium"""

import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pytest


class SimpleContrastChecker:
    """Simple color contrast checker for WCAG compliance."""
    
    def rgb_to_luminance(self, r, g, b):
        """Convert RGB to relative luminance."""
        def gamma_correct(color):
            color = color / 255.0
            return color / 12.92 if color <= 0.03928 else ((color + 0.055) / 1.055) ** 2.4
        
        return 0.2126 * gamma_correct(r) + 0.7152 * gamma_correct(g) + 0.0722 * gamma_correct(b)
    
    def contrast_ratio(self, color1, color2):
        """Calculate contrast ratio between two colors."""
        l1 = self.rgb_to_luminance(*color1)
        l2 = self.rgb_to_luminance(*color2)
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
    
    def parse_color(self, color_str):
        """Parse color string to RGB tuple."""
        if color_str.startswith('rgb'):
            match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color_str)
            if match:
                return tuple(map(int, match.groups()))
        elif color_str.startswith('#'):
            hex_color = color_str[1:]
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (0, 0, 0)  # Default to black


class SimpleKeyboardTester:
    """Simple keyboard navigation tester."""
    
    def __init__(self, driver):
        self.driver = driver
        self.actions = ActionChains(driver)
    
    def get_focusable_elements(self):
        """Get all focusable elements."""
        selector = "a, button, input, select, textarea, [tabindex]:not([tabindex='-1'])"
        return self.driver.find_elements(By.CSS_SELECTOR, selector)
    
    def press_tab(self):
        """Press Tab key."""
        self.actions.send_keys(Keys.TAB).perform()
    
    def press_enter(self):
        """Press Enter key."""
        self.actions.send_keys(Keys.ENTER).perform()
    
    def press_space(self):
        """Press Space key."""
        self.actions.send_keys(Keys.SPACE).perform()


@pytest.fixture
def ada_driver():
    """Simple fixture for Chrome driver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)
    
    yield driver
    driver.quit()


@pytest.fixture
def test_url():
    """Test URL fixture."""
    return os.getenv("ADA_TEST_URL", "http://localhost:5000")


@pytest.fixture
def contrast_checker():
    """Contrast checker fixture."""
    return SimpleContrastChecker()


@pytest.fixture
def keyboard_tester(ada_driver):
    """Keyboard tester fixture."""
    return SimpleKeyboardTester(ada_driver)