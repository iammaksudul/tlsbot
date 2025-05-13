"""TLS Contact Visa Appointment Bot with human-like behavior."""

import asyncio
import random
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from playwright.async_api import async_playwright, Browser, Page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
from .config import TLSConfig
from .logger import logger

# Browser configuration
BROWSER_CONFIG = {
    "headless": False,
    "args": [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions",
        "--ignore-certificate-errors",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-site-isolation-trials",
        "--window-size=1920,1080",
        "--start-maximized",
        "--disable-gpu",
        "--lang=en-US,en",
        "--disable-features=IsolateOrigins,site-per-process,SitePerProcess",
        "--disable-web-security",
        "--disable-notifications"
    ]
}


class AccountStatus:
    """Status tracking for TLS visa appointment accounts."""
    INIT = "INITIALIZING"  # Just started
    LOGIN_FAILED = "LOGIN FAILED"  # Failed to login
    LOGGED_IN = "LOGGED IN"  # Successfully logged in
    BOOKING = "BOOKING"  # Attempting to book
    BOOKED = "BOOKED"  # Successfully booked
    FAILED = "FAILED"  # Failed to book
    CLOUDFLARE = "CLOUDFLARE BLOCKED"  # Blocked by Cloudflare
    BOOKING_FAILED = "BOOKING FAILED"  # Failed to book appointment
    CALENDAR_ERROR = "CALENDAR ERROR"  # Error accessing calendar
    SESSION_EXPIRED = "SESSION EXPIRED"  # Session expired during booking
    NETWORK_ERROR = "NETWORK ERROR"  # Network connectivity issues
    MAINTENANCE = "SITE MAINTENANCE"  # TLS site under maintenance

class TLSVisaBot:
    """TLS Contact Visa Appointment Bot with human-like behavior."""
    
    def __init__(self):
        """Initialize the TLS Visa Bot."""
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.current_account: Optional[Dict[str, str]] = None
        self.logged_in = False
        self.current_step = 0
        self.account_history: Dict[str, Dict] = {}  # Track account history
        self.steps = [
            "Initialize Bot",              # Step 0
            "Bypass Cloudflare",          # Step 1
            "Authentication via OAuth",    # Step 2
            "Login Verification",         # Step 3
            "Country Selection",          # Step 4
            "City Selection",             # Step 5
            "Book Detail Page",           # Step 6
            "Personal Info Page",         # Step 7
            "Calendar Page",              # Step 8
            "Confirmation Page",          # Step 9
            "Payment Verification"        # Step 10
        ]
        self.results_dir = Path("results")
        self.results_dir.mkdir(exist_ok=True)
        
    def update_account_status(self, email: str, status: str, details: str = ""):
        """Update account status and history.
        
        Args:
            email: Account email
            status: New status from AccountStatus class
            details: Additional details about the status change
        """
        if email not in self.account_history:
            self.account_history[email] = {
                "status": status,
                "history": [],
                "last_updated": datetime.now().isoformat(),
                "total_attempts": 0,
                "last_error": None,
                "success": False
            }
        
        # Update status and history
        account = self.account_history[email]
        account["status"] = status
        account["total_attempts"] += 1
        
        # Track success/failure
        if status == AccountStatus.BOOKED:
            account["success"] = True
        elif status in [AccountStatus.LOGIN_FAILED, AccountStatus.FAILED, 
                       AccountStatus.BOOKING_FAILED, AccountStatus.CALENDAR_ERROR]:
            account["last_error"] = details
        
        # Add history entry
        account["history"].append({
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "details": details,
            "step": self.steps[self.current_step] if self.current_step < len(self.steps) else "Unknown",
            "attempt": account["total_attempts"]
        })
        account["last_updated"] = datetime.now().isoformat()
        
        # Save history to file
        history_file = self.results_dir / "account_history.json"
        with open(history_file, "w") as f:
            json.dump(self.account_history, f, indent=2)
            
        # Log status change
        logger.info(f"Account {email} status updated to {status}: {details}")
            
    def get_account_report(self, email: str) -> str:
        """Generate a detailed report for an account.
        
        Args:
            email: Account email to generate report for
            
        Returns:
            Formatted report string with account history and status
        """
        if email not in self.account_history:
            return f"No history found for account {email}"
            
        account = self.account_history[email]
        report = [
            f"Account Report for {email}",
            f"Current Status: {account['status']}",
            f"Total Attempts: {account['total_attempts']}",
            f"Last Updated: {account['last_updated']}",
            f"Success: {'Yes' if account['success'] else 'No'}"
        ]
        
        if account['last_error']:
            report.append(f"Last Error: {account['last_error']}")
        
        report.append("\nDetailed History:")
        
        for entry in account["history"]:
            report.append(f"\n[{entry['timestamp']}]")
            report.append(f"Attempt #{entry['attempt']}")
            report.append(f"Status: {entry['status']}")
            report.append(f"Step: {entry['step']}")
            if entry["details"]:
                report.append(f"Details: {entry['details']}")
                
        return "\n".join(report)
    
    async def _human_delay(self, min_delay=None, max_delay=None):
        """Add random delay to mimic human behavior."""
        if min_delay is None:
            min_delay = TLSConfig.TIMEOUTS["retry"]
        if max_delay is None:
            max_delay = TLSConfig.TIMEOUTS["page_load"]
        await asyncio.sleep(random.uniform(min_delay, max_delay))
    
    async def _human_type(self, selector, text):
        """Type text with human-like delays."""
        await self.page.click(selector)
        await self._human_delay(0.1, 0.3)
        await self.page.fill(selector, "")
        for char in text:
            await self.page.type(selector, char)
            await self._human_delay(0.05, 0.15)
    
    async def setup(self):
        """Set up the browser with anti-detection measures."""
        try:
            playwright = await async_playwright().start()
            
            # Use a random user agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0"
            ]
            selected_user_agent = random.choice(user_agents)
            
            # Create a browser context with enhanced anti-detection measures
            browser_context = await playwright.chromium.launch_persistent_context(
                user_data_dir="./browser_data",
                headless=BROWSER_CONFIG["headless"],
                args=BROWSER_CONFIG["args"],
                viewport={"width": random.randint(1200, 1600), "height": random.randint(800, 1000)},
                user_agent=selected_user_agent,
                locale="en-US",
                timezone_id="Europe/Paris",
                geolocation={"latitude": 48.8566, "longitude": 2.3522},
                permissions=["geolocation"],
                color_scheme="light",
                device_scale_factor=random.uniform(1.0, 2.0),
                is_mobile=False
            )
            
            self.browser = browser_context.browser
            self.page = await browser_context.new_page()
            
            # Set extra HTTP headers
            await self.page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "DNT": "1",
                "Sec-Ch-Ua": '"Chromium";v="116", "Not)A;Brand";v="24", "Google Chrome";v="116"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"'
            })
            
            # Add stealth script
            await self.page.add_init_script("""
                // Override properties that detect automation
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
                
                // Add fake plugins and mime types
                const mockPlugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'chrome-pdf-viewer' },
                    { name: 'Native Client', filename: 'native-client' }
                ];
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => mockPlugins
                });
                
                // Override other detection methods
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 10 });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                
                // Override screen properties
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
                
                // Hide automation flags
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                
                // Add WebGL support
                HTMLCanvasElement.prototype.getContext = ((old) => {
                    return function(type) {
                        const gl = old.call(this, type);
                        if (type === 'webgl') {
                            gl.getParameter = ((oldGetParameter) => {
                                return function(parameter) {
                                    if (parameter === 37445) return 'Intel Inc.';
                                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                                    return oldGetParameter.call(this, parameter);
                                };
                            })(gl.getParameter);
                        }
                        return gl;
                    };
                })(HTMLCanvasElement.prototype.getContext);
            """)
            
            return True
        except Exception as e:
            logger.error(f"Error during setup: {str(e)}")
            raise
    
    async def _handle_cloudflare(self, timeout=90):
        """Handle Cloudflare protection if present."""
        try:
            # Wait for Cloudflare challenge
            cloudflare_selectors = [
                "#challenge-running",
                "#challenge-stage",
                "#challenge-form",
                "iframe[title='Widget containing a Cloudflare security challenge']"
            ]
            
            for selector in cloudflare_selectors:
                try:
                    challenge = await self.page.wait_for_selector(selector, timeout=5000)
                    if challenge:
                        logger.info("Cloudflare challenge detected, waiting for resolution...")
                        # Wait for challenge to be solved
                        await self.page.wait_for_selector(selector, state="hidden", timeout=timeout * 1000)
                        await self._human_delay(2, 4)
                        break
                except:
                    continue
            
            # Additional wait for any redirects
            await self.page.wait_for_load_state("networkidle")
            await self._human_delay(1, 3)
            
        except Exception as e:
            logger.error(f"Error handling Cloudflare: {str(e)}")
            raise Exception("Failed to bypass Cloudflare protection")
    
    async def start_workflow(self, email, password, center):
        """Start the complete TLS visa appointment workflow."""
        try:
            # Handle Cloudflare protection
            await self._handle_cloudflare()
            
            # Navigate to login page with random delays
            await self._human_delay(2, 4)
            await self.page.goto(TLSConfig.CENTERS[center.upper()], wait_until="networkidle")
            
            # Wait for login form with retry
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    await self.page.wait_for_selector("input[type='email']", timeout=10000)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise Exception("Login form not found after retries")
                    await self._human_delay(5, 8)
                    await self.page.reload()
            
            # Fill login form with human-like behavior
            await self._human_type("input[type='email']", email)
            await self._human_delay(0.5, 1.5)
            await self._human_type("input[type='password']", password)
            await self._human_delay(1, 2)
            
            # Click login button and wait for navigation
            await self.page.click("button[type='submit']")
            await self.page.wait_for_load_state("networkidle")
            
            # Verify login success
            if await self.page.title() == "Login":
                raise Exception("Login failed - still on login page")

            # Set extra HTTP headers to appear more like a real browser
            await self.page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "DNT": "1",
                "Sec-Ch-Ua": '"Chromium";v="116", "Not)A;Brand";v="24", "Google Chrome";v="116"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"'
            })
            
            # Modify navigator properties to avoid detection
            # Add stealth script to bypass detection
            await self.page.add_init_script("""
                // Override properties that detect automation
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

                // Override permissions
                const originalQuery = window.navigator.permissions.query;
            """)
            await self.page.add_init_script("""
                window.navigator.permissions.query = (parameters) => {
                    if (parameters.name === 'notifications') {
                        return Promise.resolve({ state: Notification.permission });
                    }
                    return originalQuery.apply(this, arguments);
                };
            """)
            # The following JS block was invalid Python and caused an IndentationError. Removed for correct execution.
            # If you wish to add fake plugins/mime types, do so using add_init_script with a valid JS string, e.g.:
            await self.page.add_init_script("""
                // Override other detection methods
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 10 });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                
                // Override screen properties
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
            """)
            await self.page.add_init_script("""
                
                // Add WebGL support
                HTMLCanvasElement.prototype.getContext = ((old) => {
                    return function(type) {
                        const gl = old.call(this, type);
                        return gl;
                    };
                })(HTMLCanvasElement.prototype.getContext);
            """)
            await self._human_delay(1, 2)
            
            # Add anti-detection scripts
            await self.page.add_init_script("""
                // Override Chrome detection
                const originalHasOwnProperty = Object.prototype.hasOwnProperty;
                Object.prototype.hasOwnProperty = function(property) {
                    if (property === 'chrome') {
                        return true;
                    }
                    return originalHasOwnProperty.call(this, property);
                };
            """);
            
            # Add human-like delay
            await self._human_delay(1, 2)

            await self.page.evaluate("""
                HTMLCanvasElement.prototype.getContext = ((old) => {
                    return function(type) {
                        const gl = old.call(this, type);
                        if (type === 'webgl') {
                            gl.getParameter = ((oldGetParameter) => {
                                return function(parameter) {
                                    if (parameter === 37445) return 'Intel Inc.';
                                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                                    return oldGetParameter.call(this, parameter);
                                };
                            })(gl.getParameter);
                        }
                        return gl;
                    };
                })(HTMLCanvasElement.prototype.getContext);
            """);
            
            logger.info("Browser context setup completed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to setup browser context: {str(e)}")
            return False
        finally:
            await self._human_delay(0.5, 1)
            return True
    async def _handle_cloudflare(self, timeout=90):
        """Handle Cloudflare protection challenge."""
        try:
            cloudflare_selectors = ['#challenge-form', '#cf-challenge-form']
            for selector in cloudflare_selectors:
                try:
                    challenge = await self.page.wait_for_selector(selector, timeout=5000)
                    if challenge:
                        logger.info("Cloudflare challenge detected, waiting for resolution...")
                        # Wait for challenge to be solved
                        await self.page.wait_for_selector(selector, state="hidden", timeout=timeout * 1000)
                        await self._human_delay(2, 4)
                        break
                except Exception:
                    continue
            # Additional wait for any redirects
            await self.page.wait_for_load_state("networkidle")
            await self._human_delay(1, 3)
            return True
                
        except Exception as e:
            logger.error(f"Error handling Cloudflare: {str(e)}")
            return False

    async def login(self, email: str, password: str) -> bool:
        """Handle the login process.

        Args:
            email: User's email
            password: User's password

        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            # Fill login form
            await self._human_type("input[type='email']", email)
            await self._human_type("input[type='password']", password)
            
            # Click login button
            await self.page.click("button[type='submit']")
            await self._human_delay(2, 4)
            
            # Check for successful login
            try:
                await self.page.wait_for_selector(".dashboard", timeout=10000)
                self.logged_in = True
                logger.info(f"Successfully logged in as {email}")
                return True
            except Exception:
                # Check for error message
                error_message = await self.page.query_selector(".error-message")
                if error_message:
                    error_text = await error_message.text_content()
                    raise Exception(f"Login failed: {error_text}")
                logger.error(f"Failed to login as {email}")
                return False
        except Exception as e:
            logger.error(f"Login failed for {email}: {str(e)}")
            return False

async def start_workflow(self, email, password, center):
    """Start the complete TLS visa appointment workflow."""
    try:
        # Initialize account status and step tracking
        self.current_account = {"email": email, "current_step": 0}
        self.update_account_status(email, AccountStatus.INIT, 
            f"Starting workflow - {self.steps[0]}")
            
        # Pre-step: Setup browser if needed
        if not self.browser:
            setup_success = await self.setup()
            if not setup_success:
                raise Exception("Failed to set up browser")
            
        # Pre-step: Handle Cloudflare protection
        await self._handle_cloudflare()
        self.update_account_status(email, AccountStatus.INIT, 
            "Successfully bypassed Cloudflare")
            
        # Step 1: Navigate to login page
        self.current_step = 1
        self.update_account_status(email, AccountStatus.INIT, 
            f"Step {self.current_step}: {self.steps[self.current_step-1]}")
        await self._human_delay(2, 4)
        await self.page.goto(TLSConfig.CENTERS[center.upper()], wait_until="networkidle")
    except Exception as e:
        if isinstance(e, PlaywrightError):
            self.update_account_status(email, AccountStatus.NETWORK_ERROR, str(e))
        elif "Cloudflare" in str(e):
            self.update_account_status(email, AccountStatus.CLOUDFLARE, str(e))
        else:
            self.update_account_status(email, AccountStatus.ERROR, str(e))
        logger.error(f"Workflow failed: {str(e)}")
        raise
    finally:
        await self._human_delay(1, 2)
        
    # Step 2: Authentication via OAuth
        self.current_step = 2
        self.update_account_status(email, AccountStatus.INIT,
                                 f"Step {self.current_step}: {self.steps[self.current_step-1]} - Waiting for login form")
        
        # Wait for login form with retry
        max_retries = 3
        retry_count = 0
        login_form_found = False
        
        while retry_count < max_retries:
            try:
                await self.page.wait_for_selector("input[type='email']", timeout=10000)
                login_form_found = True
                self.update_account_status(email, AccountStatus.INIT,
                    f"Step {self.current_step}: Login form found, starting authentication")
                break
            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    self.update_account_status(email, AccountStatus.LOGIN_FAILED, 
                        f"Step {self.current_step}: Login form not found after {max_retries} retries")
                    raise Exception("Login form not found after retries")
                self.update_account_status(email, AccountStatus.INIT,
                    f"Step {self.current_step}: Retrying to find login form (attempt {retry_count}/{max_retries})")
                await self._human_delay(5, 8)
                await self.page.reload()
        # Step 2: Login
        try:
            login_success = await self.login(email, password)
            if not login_success:
                raise Exception("Login failed")
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            self.update_account_status(email, AccountStatus.LOGIN_FAILED, "Failed to authenticate")
            raise Exception("Login failed")
            
        self.update_account_status(email, AccountStatus.LOGGED_IN,
            f"Step {self.current_step}: Successfully authenticated")
            
        # Step 3: Move to booking process
        self.current_step = 3
        self.update_account_status(email, AccountStatus.BOOKING,
            f"Step {self.current_step}: {self.steps[self.current_step-1]} - Starting appointment booking")

async def _handle_cloudflare(self, timeout=90):
    """Handle Cloudflare protection if present with advanced techniques."""
    try:
        # Wait for Cloudflare challenge
        cloudflare_selectors = [
            "#challenge-running",
            "#challenge-stage",
            "#challenge-form",
            "iframe[title='Widget containing a Cloudflare security challenge']"
        ]
            
        for selector in cloudflare_selectors:
            try:
                challenge = await self.page.wait_for_selector(selector, timeout=5000)
                if challenge:
                    logger.info("Cloudflare challenge detected, waiting for resolution...")
                    # Wait for challenge to be solved
                    await self.page.wait_for_selector(selector, state="hidden", timeout=timeout * 1000)
                    await self._human_delay(2, 4)
                    break
            except Exception as e:
                logger.debug(f"Selector {selector} not found: {str(e)}")
                continue
            
        # Additional wait for any redirects
        await self.page.wait_for_load_state("networkidle")
        await self._human_delay(1, 3)
            
    except Exception as e:
        logger.error(f"Error handling Cloudflare: {str(e)}")
        raise Exception("Failed to bypass Cloudflare protection")


async def login(self, email: str, password: str) -> bool:
    """Handle the login process.
        
    Args:
        email: User's email
        password: User's password
            
    Returns:
        bool: True if login successful, False otherwise
    """
    try:
        # Fill login form
        await self._human_type("input[type='email']", email)
        await self._human_delay(0.5, 1.5)
        await self._human_type("input[type='password']", password)
        await self._human_delay(1, 2)
        
        # Click login button
        login_button = await self.page.wait_for_selector("button[type='submit']", timeout=5000)
        if not login_button:
            raise Exception("Login button not found")
        
        await login_button.click()
        await self._human_delay(2, 3)
        
        # Wait for successful login redirect or error message
        try:
            await self.page.wait_for_selector(".user-info, .error-message", timeout=10000)
        except Exception:
            raise Exception("Login verification timeout")
        
        # Check if login was successful
        error_message = await self.page.query_selector(".error-message")
        if error_message:
            error_text = await error_message.text_content()
            raise Exception(f"Login failed: {error_text}")
            
        self.logged_in = True
        return True
            
    except Exception as e:
        logger.error(f"Login failed for {email}: {str(e)}")
        return False

async def _human_delay(self, min_delay=None, max_delay=None):
    """Add random delay to mimic human behavior."""
    min_delay = min_delay or TLSConfig.TIMEOUTS["retry"]
    max_delay = max_delay or TLSConfig.TIMEOUTS["page_load"]
    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)

async def _human_type(self, selector, text):
    """Type text with human-like delays."""
    try:
        await self.page.click(selector)
        for char in text:
            await self.page.type(selector, char)
            await asyncio.sleep(random.uniform(
                TIMING["typing_delay_min"], 
                TIMING["typing_delay_max"]
            ))
    except Exception as e:
        logger.error(f"Error during human typing: {str(e)}")
        raise

async def _human_scroll(self):
    """Scroll the page like a human with more natural patterns."""
    try:
        # Get page height
        page_height = await self.page.evaluate('document.body.scrollHeight')
        viewport_height = await self.page.evaluate('window.innerHeight')
            
        if page_height <= viewport_height:
            # Page fits in viewport, no need to scroll
            return
            
        # Start with a slight pause before scrolling
        await self._human_delay(0.5, 1.5)
            
        # Scroll down with natural speed variations
        current_scroll = 0
        while current_scroll < page_height:
            step = random.randint(100, 300)
            await self.page.evaluate(f'window.scrollBy(0, {step})')
            current_scroll += step
            await self._human_delay(0.1, 0.3)
                
            # Random pauses
            if random.random() < 0.2:  # 20% chance to pause
                await self._human_delay(0.5, 1.0)
            
        # Wait at bottom
        await self._human_delay(1, 2)
            
        # Scroll back up with variations
        while current_scroll > 0:
            step = random.randint(100, 300)
            current_scroll = max(0, current_scroll - step)
                    
            await self.page.evaluate(f'window.scrollBy(0, -{step})')
            await self._human_delay(0.1, 0.3)
                
            # Occasionally move the mouse while scrolling
            if random.random() < 0.3:  # 30% chance
                x = random.randint(100, 500)
                y = random.randint(100, 500)
                await self.page.mouse.move(x, y)
    except Exception as e:
        logger.error(f"Error during human scrolling: {str(e)}")
        raise
    finally:
        await self._human_delay(0.5, 1)

async def send_security_notification(self, issue_type, details, account_email=None):
    """Send security notification email to developer."""
    
    async def login(self, email: str, password: str) -> bool:
        """Handle the login process.

        Args:
            email: User's email
            password: User's password

        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            # Fill login form
            await self._human_type("input[type='email']", email)
            await self._human_delay(0.5, 1.5)
            await self._human_type("input[type='password']", password)
            await self._human_delay(1, 2)
            
            # Click login button
            login_button = await self.page.wait_for_selector("button[type='submit']", timeout=5000)
            if not login_button:
                raise Exception("Login button not found")
            
            await login_button.click()
            await self._human_delay(2, 3)
            
            # Wait for successful login redirect or error message
            try:
                await self.page.wait_for_selector(".user-info, .error-message", timeout=10000)
            except Exception:
                raise Exception("Login verification timeout")
            
            # Check if login was successful
            error_message = await self.page.query_selector(".error-message")
            if error_message:
                error_text = await error_message.text_content()
                raise Exception(f"Login failed: {error_text}")
            
            self.logged_in = True
            return True
            
        except Exception as e:
            logger.error(f"Login failed for {email}: {str(e)}")
            return False

    async def start_workflow(self, email, password, center):
        """Start the complete TLS visa appointment workflow."""
        try:
            # Initialize account status and step tracking
            self.current_account = {"email": email, "current_step": 0}
            self.update_account_status(email, AccountStatus.INIT, 
                f"Starting workflow - {self.steps[0]}")
            
            # Pre-step: Setup browser if needed
            if not self.browser:
                setup_success = await self.setup()
                if not setup_success:
                    raise Exception("Failed to set up browser")
            
            # Pre-step: Handle Cloudflare protection
        except Exception as e:
            logger.error(f"Failed to navigate to booking: {str(e)}")
            self.update_account_status(email, AccountStatus.FAILED)
            return False

        # Step 4: Select center
        try:
            await self.page.select_option('select#VisaCenter', center)
            await self._human_delay(1, 2)
        except Exception as e:
            logger.error(f"Failed to select center: {str(e)}")
            self.update_account_status(email, AccountStatus.FAILED)
            return False

        # Step 5: Check calendar
        try:
            calendar = await self.page.query_selector('.calendar')
            if not calendar:
                logger.error("Calendar not found")
                self.update_account_status(email, AccountStatus.CALENDAR_ERROR)
                return False

            available_dates = await calendar.query_selector_all('.available')
            if not available_dates:
                logger.info("No available dates found")
                self.update_account_status(email, AccountStatus.BOOKING_FAILED)
                return False

            # Select first available date
            await available_dates[0].click()
            await self._human_delay(1, 2)
        except Exception as e:
            logger.error(f"Error checking calendar: {str(e)}")
            self.update_account_status(email, AccountStatus.CALENDAR_ERROR)
            return False

        # Step 6: Complete booking
        try:
            await self.page.click('button[type="submit"]')
            await self.page.wait_for_selector('.confirmation', timeout=10000)
            self.update_account_status(email, AccountStatus.BOOKED)
            return True
        except Exception as e:
            logger.error(f"Failed to complete booking: {str(e)}")
            self.update_account_status(email, AccountStatus.BOOKING_FAILED)
            return False

    async def start_workflow(self, email, password, center):
        """Start the complete TLS visa appointment workflow."""
        try:
            # Initialize account status and step tracking
            self.current_account = {"email": email, "current_step": 0}
            self.update_account_status(email, AccountStatus.INIT, 
                f"Starting workflow - {self.steps[0]}")
            
            # Pre-step: Setup browser if needed
            if not self.browser:
                setup_success = await self.setup()
                if not setup_success:
                    raise Exception("Failed to set up browser")
            
            # Pre-step: Handle Cloudflare protection
            await self._handle_cloudflare()
            self.update_account_status(email, AccountStatus.INIT, 
                "Successfully bypassed Cloudflare")
            
            # Step 1: Navigate to login page
            self.current_step = 1
            self.update_account_status(email, AccountStatus.INIT, 
                f"Step {self.current_step}: {self.steps[self.current_step-1]}")
            await self._human_delay(2, 4)
            await self.page.goto(TLSConfig.CENTERS[center.upper()], wait_until="networkidle")
        except Exception as e:
            if isinstance(e, PlaywrightError):
                self.update_account_status(email, AccountStatus.NETWORK_ERROR, str(e))
            elif "Cloudflare" in str(e):
                self.update_account_status(email, AccountStatus.CLOUDFLARE, str(e))
            else:
                self.update_account_status(email, AccountStatus.ERROR, str(e))
            logger.error(f"Workflow failed: {str(e)}")
            raise
            # Pre-step: Setup browser if needed
            if not self.browser:
                setup_success = await self.setup()
                if not setup_success:
                    raise Exception("Failed to set up browser")
        
        # Pre-step: Handle Cloudflare protection
        await self._handle_cloudflare()
        self.update_account_status(email, AccountStatus.INIT, 
            "Successfully bypassed Cloudflare")
        
        await self._human_delay(1, 2)
        while retry_count < max_retries:
            try:
                await self.page.wait_for_selector("input[type='email']", timeout=10000)
                login_form_found = True
                self.update_account_status(email, AccountStatus.INIT,
                    f"Step {self.current_step}: Login form found, starting authentication")
                break
            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    self.update_account_status(email, AccountStatus.LOGIN_FAILED, 
                        f"Step {self.current_step}: Login form not found after {max_retries} retries")
                    raise Exception("Login form not found after retries")
                self.update_account_status(email, AccountStatus.INIT,
                    f"Step {self.current_step}: Retrying to find login form (attempt {retry_count}/{max_retries})")
                await self._human_delay(5, 8)
                await self.page.reload()

    async def login(self, email: str, password: str) -> bool:
        """Handle the login process.
    
        Args:
            email: User's email
            password: User's password
        
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            # Fill login form
            await self._human_type("input[type='email']", email)
            await self._human_delay(0.5, 1.5)
            await self._human_type("input[type='password']", password)
            await self._human_delay(1, 2)
        
            # Click login button
            login_button = await self.page.wait_for_selector("button[type='submit']", timeout=5000)
            if not login_button:
                raise Exception("Login button not found")
        
            await login_button.click()
            await self._human_delay(2, 3)
        
            # Wait for successful login redirect or error message
            try:
                await self.page.wait_for_selector(".user-info, .error-message", timeout=10000)
            except Exception:
                raise Exception("Login verification timeout")
        
            # Check if login was successful
            error_message = await self.page.query_selector(".error-message")
            if error_message:
                error_text = await error_message.text_content()
                raise Exception(f"Login failed: {error_text}")
        
            self.logged_in = True
            return True
        
        except Exception as e:
            # Pre-step: Handle Cloudflare protection
            try:
                await self._handle_cloudflare()
                self.update_account_status(email, AccountStatus.INIT, 
                    "Successfully bypassed Cloudflare")
            except Exception as cf_error:
                self.update_account_status(email, AccountStatus.CLOUDFLARE, str(cf_error))
                raise
            
            # Step 1: Navigate to login page
            try:
                self.current_step = 1
                self.update_account_status(email, AccountStatus.INIT, 
                    f"Step {self.current_step}: {self.steps[self.current_step-1]}")
                await self._human_delay(2, 4)
                await self.page.goto(TLSConfig.CENTERS[center.upper()], wait_until="networkidle")
            except Exception as nav_error:
                self.update_account_status(email, AccountStatus.NETWORK_ERROR, str(nav_error))
                raise
        
            # Step 2: Authentication via OAuth
            self.current_step = 2
            self.update_account_status(email, AccountStatus.INIT,
                f"Step {self.current_step}: {self.steps[self.current_step-1]} - Waiting for login form")
        
            # Wait for login form with retry
            max_retries = 3
            retry_count = 0
            login_form_found = False
        
            while retry_count < max_retries:
                try:
                    await self.page.wait_for_selector("input[type='email']", timeout=10000)
                    login_form_found = True
                    self.update_account_status(email, AccountStatus.INIT,
                        f"Step {self.current_step}: Login form found, starting authentication")
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        self.update_account_status(email, AccountStatus.LOGIN_FAILED, 
                            f"Step {self.current_step}: Login form not found after {max_retries} retries")
                        raise Exception("Login form not found after retries")
                    self.update_account_status(email, AccountStatus.INIT,
                        f"Step {self.current_step}: Retrying to find login form (attempt {retry_count}/{max_retries})")
                    await self._human_delay(5, 8)
                    await self.page.reload()
            # Step 2: Login
            try:
                login_success = await self.login(email, password)
                if not login_success:
                    raise Exception("Login failed")
            except Exception as e:
                logger.error(f"Login failed: {str(e)}")
                self.update_account_status(email, AccountStatus.LOGIN_FAILED, "Failed to authenticate")
                raise Exception("Login failed")
            
            self.update_account_status(email, AccountStatus.LOGGED_IN,
                f"Step {self.current_step}: Successfully authenticated")
            
            # Step 3: Move to booking process
            self.current_step = 3
            self.update_account_status(email, AccountStatus.BOOKING,
                f"Step {self.current_step}: {self.steps[self.current_step-1]} - Starting appointment booking")

    async def _handle_cloudflare(self, timeout=90):
        """Handle Cloudflare protection if present with advanced techniques."""
        try:
            # Wait for Cloudflare challenge
            cloudflare_selectors = [
                "#challenge-running",
                "#challenge-stage",
                "#challenge-form",
                "iframe[title='Widget containing a Cloudflare security challenge']"
            ]
            
            for selector in cloudflare_selectors:
                try:
                    challenge = await self.page.wait_for_selector(selector, timeout=5000)
                    if challenge:
                        logger.info("Cloudflare challenge detected, waiting for resolution...")
                        # Wait for challenge to be solved
                        await self.page.wait_for_selector(selector, state="hidden", timeout=timeout * 1000)
                        await self._human_delay(2, 4)
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} not found: {str(e)}")
                    continue
            
            # Additional wait for any redirects
            await self.page.wait_for_load_state("networkidle")
            await self._human_delay(1, 3)
            
        except Exception as e:
            logger.error(f"Error handling Cloudflare: {str(e)}")
            raise Exception("Failed to bypass Cloudflare protection")


async def login(self, email: str, password: str) -> bool:
    """Handle the login process.
    
    Args:
        email: User's email
        password: User's password
        
    Returns:
        bool: True if login successful, False otherwise
    """
    try:
        # Fill login form
        await self._human_type("input[type='email']", email)
        await self._human_delay(0.5, 1.5)
        await self._human_type("input[type='password']", password)
        await self._human_delay(1, 2)
        
        # Click login button
        login_button = await self.page.wait_for_selector("button[type='submit']", timeout=5000)
        if not login_button:
            raise Exception("Login button not found")
        
        await login_button.click()
        await self._human_delay(2, 3)
        
        # Wait for successful login redirect or error message
        try:
            await self.page.wait_for_selector(".user-info, .error-message", timeout=10000)
        except Exception:
            raise Exception("Login verification timeout")
        
        # Check if login was successful
        error_message = await self.page.query_selector(".error-message")
        if error_message:
            error_text = await error_message.text_content()
            raise Exception(f"Login failed: {error_text}")
        
        self.logged_in = True
        return True
        
    except Exception as e:
        logger.error(f"Login failed for {email}: {str(e)}")
        return False

async def start_workflow(self, email, password, center):
    """Start the complete TLS visa appointment workflow."""
    try:
        # Initialize account status and step tracking
        self.current_account = {"email": email, "current_step": 0}
        self.update_account_status(email, AccountStatus.INIT, 
            f"Starting workflow - {self.steps[0]}")
        
        # Pre-step: Handle Cloudflare protection
        try:
            await self._handle_cloudflare()
            self.update_account_status(email, AccountStatus.INIT, 
                "Successfully bypassed Cloudflare")
        except Exception as cf_error:
            self.update_account_status(email, AccountStatus.CLOUDFLARE, str(cf_error))
            raise
        
        # Step 1: Navigate to login page
        try:
            self.current_step = 1
            self.update_account_status(email, AccountStatus.INIT, 
                f"Step {self.current_step}: {self.steps[self.current_step-1]}")
            await self._human_delay(2, 4)
            await self.page.goto(TLSConfig.CENTERS[center.upper()], wait_until="networkidle")
        except Exception as nav_error:
            self.update_account_status(email, AccountStatus.NETWORK_ERROR, str(nav_error))
            raise
        
        # Step 2: Authentication via OAuth
        self.current_step = 2
        self.update_account_status(email, AccountStatus.INIT,
            f"Step {self.current_step}: {self.steps[self.current_step-1]} - Waiting for login form")
        
        # Wait for login form with retry
        max_retries = 3
        retry_count = 0
        login_form_found = False
        
        while retry_count < max_retries:
            try:
                await self.page.wait_for_selector("input[type='email']", timeout=10000)
                login_form_found = True
                self.update_account_status(email, AccountStatus.INIT,
                    f"Step {self.current_step}: Login form found, starting authentication")
                break
            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    self.update_account_status(email, AccountStatus.LOGIN_FAILED, 
                        f"Step {self.current_step}: Login form not found after {max_retries} retries")
                    raise Exception("Login form not found after retries")
                self.update_account_status(email, AccountStatus.INIT,
                    f"Step {self.current_step}: Retrying to find login form (attempt {retry_count}/{max_retries})")
                await self._human_delay(5, 8)
                await self.page.reload()
        
        # Attempt login
        login_success = await self.login(email, password)
        if not login_success:
            self.update_account_status(email, AccountStatus.LOGIN_FAILED, "Failed to authenticate")
            raise Exception("Login failed")
        
        self.update_account_status(email, AccountStatus.LOGGED_IN,
            f"Step {self.current_step}: Successfully authenticated")
        
        # Move to booking process
        self.current_step = 3
        self.update_account_status(email, AccountStatus.BOOKING, 
            f"Step {self.current_step}: {self.steps[self.current_step-1]} - Starting appointment booking")
        
        # Step 4: Navigate to Country Selection
        self.current_step = 4
        self.update_account_status(email, AccountStatus.BOOKING,
            f"Step {self.current_step}: {self.steps[self.current_step-1]} - Selecting country")
        
        # Navigate to the main country page
        try:
            await self.page.goto(TLSConfig.BASE_URL)
            await self._human_delay(2, 4)
            
        except Exception as nav_error:
            self.update_account_status(email, AccountStatus.NETWORK_ERROR,
                f"Step {self.current_step}: Navigation error - {str(nav_error)}")
            raise
            
            # Step 4: Navigate to Country Selection
            self.current_step = 4
            self.update_account_status(email, AccountStatus.BOOKING,
                f"Step {self.current_step}: {self.steps[self.current_step-1]} - Selecting country")
            
            # Navigate to the main country page
            try:
                await self.page.goto(TLSConfig.BASE_URL)
                await self.page.wait_for_load_state('networkidle')
                self.update_account_status(email, AccountStatus.BOOKING,
                    f"Step {self.current_step}: Successfully loaded country selection page")
            except Exception as nav_error:
                self.update_account_status(email, AccountStatus.NETWORK_ERROR, 
                    f"Step {self.current_step}: Failed to navigate to country page - {str(nav_error)}")
                raise
            
            # Handle Cloudflare if present
            try:
                if not await self._handle_cloudflare():
                    self.update_account_status(email, AccountStatus.CLOUDFLARE, 
                        f"Step {self.current_step}: Failed to bypass Cloudflare protection")
                    raise Exception("Failed to bypass Cloudflare protection")
                self.update_account_status(email, AccountStatus.BOOKING,
                    f"Step {self.current_step}: Successfully bypassed Cloudflare")
            except Exception as cf_error:
                self.update_account_status(email, AccountStatus.CLOUDFLARE, 
                    f"Step {self.current_step}: Cloudflare error - {str(cf_error)}")
                raise
            
            await self._human_delay()
            await self._human_scroll()
            
            # Step 5: City Selection
            self.current_step = 5
            self.update_account_status(email, AccountStatus.BOOKING,
                f"Step {self.current_step}: {self.steps[self.current_step-1]} - Selecting city {center}")
            
            # Map center code to URL
            center_upper = center.upper()
            self.update_account_status(email, AccountStatus.BOOKING,
                f"Step {self.current_step}: Navigating to {center_upper} appointment center")
            if center_upper not in TLSConfig.AUTH_PARAMS:
                await self.send_security_notification(
                    "Invalid Center",
                    f"Unknown center code: {center}. Bot cannot proceed with workflow.",
                    email
                )
                raise Exception(f"Unknown center: {center}")
            
            # Use the exact URL from the configuration
            city_url = TLSConfig.CENTERS[center_upper()]
            
            # Navigate to the city-specific page
            await self.page.goto(city_url)
            await self.page.wait_for_load_state('networkidle')
            
            # Handle Cloudflare if present
            if not await self._handle_cloudflare():
                await self.send_security_notification(
                    "Cloudflare Detection",
                    f"Failed to bypass Cloudflare protection on {center} page. Bot was likely detected.",
                    email
                )
                raise Exception(f"Failed to bypass Cloudflare protection on {center} page")
            
            await self._human_delay()
            
            # Step 3: Authentication via OAuth
            self.current_step = 3
            logger.info(f"Step {self.current_step}: {self.steps[self.current_step-1]}")
            
            # Look for login button and click it
            login_button = await self.page.query_selector('a:text("Login"), button:text("Login"), a:text("Sign in")')
            if login_button:
                await login_button.click()
                await self.page.wait_for_load_state('networkidle')
            
            # Wait for login form with retry
            login_form_found = False
            for attempt in range(3):
                try:
                    await self.page.wait_for_selector('input[type="email"], input[name="username"]', timeout=5000)
                    login_form_found = True
                    break
                except Exception:
                    logger.warning(f"Login form not found on attempt {attempt+1}/3")
                    await self._human_delay()
                    await self.page.reload()
                    await self.page.wait_for_load_state('networkidle')
            
            if not login_form_found:
                await self.send_security_notification(
                    "Authentication Form Changed",
                    "Login form selectors no longer match. The website may have changed its authentication mechanism.",
                    email
                )
                raise Exception("Could not find login form after multiple attempts")
            
            # Fill in email/username
            email_field = await self.page.query_selector('input[type="email"], input[name="username"]')
            if email_field:
                await self._human_type('input[type="email"], input[name="username"]', email)
            else:
                raise Exception("Could not find email input field")
            
            # Move to password field and fill it
            password_field = await self.page.query_selector('input[type="password"]')
            if password_field:
                await self._human_delay()
                await self._human_type('input[type="password"]', password)
            else:
                raise Exception("Could not find password input field")
            
            # Click login button
            await self._human_delay()
            submit_button = await self.page.query_selector('button[type="submit"], input[type="submit"]')
            if submit_button:
                await submit_button.click()
                await self.page.wait_for_navigation()
                await self.page.wait_for_load_state('networkidle')
            else:
                raise Exception("Could not find login submit button")
            
            # Verify successful login
            is_logged_in = await self.page.query_selector('.user-profile, .user-account, .account-info, .logout-link')
            if not is_logged_in:
                await self.send_security_notification(
                    "Authentication Failure",
                    "Login appeared to succeed but could not detect logged-in state. The website may have changed its authentication flow or credentials are invalid.",
                    email
                )
                raise Exception("Login failed - could not detect logged in state")
            
            logger.info(f"Successfully logged in with {email}")
            self.current_account = {
                "email": email,
                "password": password,
                "center": center
            }
            self.logged_in = True
            
            # Step 4: Book Detail Page
            self.current_step = 4
            logger.info(f"Step {self.current_step}: {self.steps[self.current_step-1]}")
            
            # Navigate to the booking details page
            form_group_url = f"https://fr.tlscontact.com/formGroup/ma/{center_code}"
            logger.info(f"[NAVIGATION] Attempting to go to: {form_group_url}")
            await self.page.goto(form_group_url)
            logger.info(f"[NAVIGATION] After goto: page.url={self.page.url}")
            import sys
            for handler in logger.handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            if self.page.url == 'about:blank':
                content = await self.page.content()
                logger.error(f"[ERROR] Landed on about:blank. Page content (first 500 chars): {content[:500]}")
                for handler in logger.handlers:
                    if hasattr(handler, 'flush'):
                        handler.flush()
            await self.page.wait_for_load_state('networkidle')
            
            # Handle any forms if needed
            await self._human_delay()
            await self._human_scroll()
            
            # Look for and fill any required form fields
            form_fields = await self.page.query_selector_all('input[required], select[required]')
            for field in form_fields:
                field_type = await field.get_attribute('type')
                if field_type in ['text', 'email', 'tel']:
                    await field.fill('Sample text')
                elif field_type == 'checkbox':
                    await field.check()
                elif await field.get_attribute('tagName') == 'SELECT':
                    # Select first non-empty option
                    options = await field.query_selector_all('option')
                    for option in options:
                        value = await option.get_attribute('value')
                        if value and value != '':
                            await field.select_option(value)
                            break
                
                # Submit form if present
                submit_button = await self.page.query_selector('button[type="submit"]:visible')
                if submit_button:
                    await submit_button.click()
                    await self.page.wait_for_navigation()
                    await self.page.wait_for_load_state('networkidle')
                
                # Step 5: Personal Info Page
                self.current_step = 5
                logger.info(f"Step {self.current_step}: {self.steps[self.current_step-1]}")
                
                # Look for and click the "Book Appointment" button
                await self._human_delay()
                book_button = await self.page.query_selector('a:text("Book Appointment"), button:text("Book Appointment"), a:text("Book an appointment")')
                if book_button:
                    await book_button.click()
                    await self.page.wait_for_navigation()
                    await self.page.wait_for_load_state('networkidle')
                else:
                    logger.warning("Could not find Book Appointment button")
                
                # Step 6: Calendar Page
            self.current_step = 6
            logger.info(f"Step {self.current_step}: {self.steps[self.current_step-1]}")
            
            # Start monitoring for available dates
            appointment_found = await self._monitor_calendar()
            
            if appointment_found:
                # Step 7: Confirmation Page
                self.current_step = 7
                logger.info(f"Step {self.current_step}: {self.steps[self.current_step-1]}")
                
                # Click confirm button
                await self._human_delay()
                confirm_button = await self.page.query_selector('button:text("Confirm"), input[value="Confirm"]')
                if confirm_button:
                    await confirm_button.click()
                    await self.page.wait_for_navigation()
                    await self.page.wait_for_load_state('networkidle')
                    
                    # Step 8: Stop at Payment
                    self.current_step = 8
                    logger.info(f"Step {self.current_step}: {self.steps[self.current_step-1]}")
                    logger.info("Reached payment page. Stopping as requested.")
                    
                    # Save booking details
                    booking_details = {
                        "email": email,
                        "center": center,
                        "timestamp": datetime.now().isoformat(),
                        "payment_url": self.page.url
                    }
                    await self._save_booking(booking_details)
                    

# ... (rest of the code remains the same)
                # No dates available, wait and retry
                await asyncio.sleep(random.uniform(3, 5))

                # Refresh the page occasionally
                if random.random() < 0.1:  # 10% chance to refresh
                    logger.info("Refreshing calendar page")
                    await self.page.reload()
                    await self.page.wait_for_load_state('networkidle')

        logger.warning("Monitoring time limit reached without finding available dates")

        # Notify developer about potential selector changes if we never found dates
        if self.current_account and random.random() < 0.1:  # Only send occasionally (10% chance)
            await self.send_security_notification(
                "Calendar Selectors May Have Changed",
                "Bot monitored the calendar page for the maximum time but couldn't find any available dates. This could be normal (no appointments available) or the calendar selectors may have changed.",
                self.current_account.get("email")
            )

        return False
    except Exception as e:
        logger.error(f"Failed to monitor calendar: {str(e)}")
        raise
    finally:
        await self._human_delay(1, 2)
        await self._human_delay(1, 2)

    async def _save_booking(self, booking_details):
        """Save booking details to file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.results_dir / f"booking_{timestamp}.json"

            with open(filename, 'w') as f:
                json.dump(booking_details, f, indent=2)

            logger.info(f"Booking details saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Error saving booking details: {str(e)}")
            return False

    async def send_security_notification(self, issue_type, details, account_email=None):
        """Send security notification email to developer.

        Args:
            issue_type: Type of security issue
            details: Additional details about the issue
            account_email: Optional email of affected account
        """
        try:
            # Create email content
            subject = f"TLS Bot Security Alert: {issue_type}"
            body = f"Security Issue Detected\n\n"
            body += f"Type: {issue_type}\n"
            body += f"Details: {details}\n"
            if account_email:
                body += f"Account: {account_email}\n"
            body += f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

            # Save to log file
            log_file = self.results_dir / "security_alerts.log"
            with open(log_file, "a") as f:
                f.write(f"\n{'='*50}\n")
                f.write(body)

            logger.warning(f"Security alert logged: {issue_type}")
            return True

        except Exception as e:
            logger.error(f"Error sending security notification: {str(e)}")
            return False

    async def close(self):
        """Close the browser and clean up resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None

async def main():
    """Main function to run the bot."""
    bot = TLSVisaBot()
    try:
        await bot.setup()
        # Add your workflow here
        pass
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
