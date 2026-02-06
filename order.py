import json, requests, sys, urllib.parse, re, time, threading, logging, html, random, uuid, os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from datetime import datetime, timezone
import telebot
from telebot import types
from urllib.parse import urlencode, unquote
import socket

# ---------------- CONFIG ----------------
TELEGRAM_BOT_TOKEN = "8509627011:AAEh_FVpaAY-_f7_9LPO1x7__zbHY00ymsM"
ADMIN_CHAT_ID = "5805230405"
CHECK_INTERVAL_SECONDS = 5.0
MONITOR_LOOP_SLEEP = 2.0

PINCODE = "211003"
USER_EMAIL = "leongamer276657@gmail.com"
USER_MOBILE = "9695576069"

AD_ID = '968777a5-36e1-42a8-9aad-3dc36c3f77b2'
PAYMENT_METHOD = "UPI"

# Endpoints
URL_MICROCART = "https://www.sheinindia.in/api/cart/microcart"
URL_DELETE = "https://www.sheinindia.in/api/cart/delete"
URL_CREATE = "https://www.sheinindia.in/api/cart/create"
URL_ADD_FMT = "https://www.sheinindia.in/api/cart/{cart_id}/product/{product_id}/add"
URL_APPLY_VOUCHER = "https://www.sheinindia.in/api/cart/apply-voucher"
URL_SERVICE_CHECK = "https://www.sheinindia.in/api/edd/checkDeliveryDetails"
URL_BANNER_INFO = "https://www.sheinindia.in/api/my-account/banner-info"
URL_PAY_STAGE2 = "https://payment.sheinindia.in/pay"
URL_PAY_NOW = "https://payment.sheinindia.in/payment-engine/api/v1/payment/pay-now"
URL_APP_ADDRESS = "https://www.sheinindia.in/checkout/address/getAddressList"
URL_ADDRESS_BOOK = "https://www.sheinindia.in/my-account/address-book"

COMMON_HEADERS = {
    "sec-ch-ua-platform": '"Android"',
    "user-agent": "Mozilla/5.0 (Linux; Android 10; RMX2030 Build/QKQ1.200209.002) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142 Mobile Safari/537.36",
    "x-tenant-id": "SHEIN",
    "accept-language": "en-US,en;q=0.9"
}
HEADERS_JSON = {
    **COMMON_HEADERS,
    "accept": "application/json",
    "content-type": "application/json",
    "referer": "https://www.sheinindia.in/cart?user=old"
}

# ---------------- User Sessions Storage ----------------
USER_SESSIONS = {}
WATCHLIST = {}
MONITOR_RUNNING = threading.Event()
BOT_STOPPED = threading.Event()

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("shein_autobuyer")

# Initialize bot with better error handling
try:
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode=None, threaded=True)
    logger.info("Bot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    sys.exit(1)

# ---------------- Connection Test Functions ----------------
def test_connection():
    """Test if we can connect to Shein servers"""
    test_urls = [
        "https://api.sheinindia.in",
        "https://www.sheinindia.in",
        "https://payment.sheinindia.in"
    ]
    
    for url in test_urls:
        try:
            # Try to get IP address first
            domain = url.split('//')[1].split('/')[0]
            logger.info(f"Resolving {domain}...")
            ip = socket.gethostbyname(domain)
            logger.info(f"✓ {domain} resolves to {ip}")
            
            # Try HTTP connection
            logger.info(f"Testing connection to {url}...")
            response = requests.head(url, timeout=10)
            logger.info(f"✓ {url} - Status: {response.status_code}")
            return True
        except socket.gaierror as e:
            logger.error(f"✗ DNS resolution failed for {domain}: {e}")
        except requests.exceptions.ConnectTimeout:
            logger.error(f"✗ Connection timeout to {url}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"✗ Connection error to {url}: {e}")
        except Exception as e:
            logger.error(f"✗ Error testing {url}: {e}")
    
    return False

def make_session_with_retries(total=5, backoff=2, status_forcelist=(429,500,502,503,504)):
    """Create a session with retry logic"""
    s = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=total,
        backoff_factor=backoff,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
        raise_on_status=False
    )
    
    # Mount adapter for both HTTP and HTTPS
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=100,
        pool_maxsize=100
    )
    
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    
    # Increase default timeout
    s.request = lambda method, url, **kwargs: requests.Session.request(
        s, method, url, timeout=(30, 60), **kwargs
    )
    
    return s

# module-level session used by `req()` when no explicit session is available
SESSION = make_session_with_retries()

# ---------------- Helper Functions ----------------
def get_random_ip():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}"

def get_android_headers(additional_headers=None):
    headers = {
        'User-Agent': 'Shein/8.5.1 (Android 29; Build/SM-G973F)',
        'Client_type': 'Android/29',
        'Client_version': '8.5.1',
        'X-Tenant-Id': 'SHEIN',
        'X-Tenant': 'B2C',
        'Ad_id': AD_ID,
        'Host': 'api.sheinindia.in',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip',
        'Accept-Language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    if additional_headers:
        headers.update(additional_headers)
    return headers

def tg_send(chat_id, text):
    try:
        bot.send_message(chat_id, text)
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")

def safe_json(r):
    try:
        return r.json()
    except:
        return None

def req(method, url, headers=None, cookies=None, body=None, params=None, allow_redirects=True, timeout=(30, 60), return_resp=False, session=None):
    """Make an HTTP request with retries."""
    headers = headers or HEADERS_JSON
    sess = session or SESSION
    
    # Add random delay to avoid rate limiting
    time.sleep(random.uniform(0.5, 1.5))
    
    try:
        logger.info(f"Making {method} request to {url}")
        
        if method == "GET":
            r = sess.get(url, headers=headers, cookies=cookies, params=params, allow_redirects=allow_redirects, timeout=timeout)
        else:
            r = sess.post(url, headers=headers, cookies=cookies, data=body, params=params, allow_redirects=allow_redirects, timeout=timeout)
            
        logger.info(f"Response status: {r.status_code}")
        
        data = safe_json(r)
        ok = (200 <= r.status_code < 300)
        
        if return_resp:
            return r, data, ok
        return r, data, ok
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error {method} {url}: {e}")
        return None, None, False
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error {method} {url}: {e}")
        return None, None, False
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error {method} {url}: {e}")
        return None, None, False
    except Exception as e:
        logger.error(f"Unexpected error {method} {url}: {e}")
        return None, None, False

# ---------------- Login Functions ----------------
def get_client_token(session):
    """Get client access token with improved error handling"""
    url = "https://api.sheinindia.in/uaas/jwt/token/client"
    headers = get_android_headers({
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'api.sheinindia.in'
    })
    data = "grantType=client_credentials&clientName=trusted_client&clientSecret=secret"
    
    try:
        logger.info(f"Requesting client token from {url}")
        
        # Try with longer timeout
        resp = session.post(url, data=data, headers=headers, timeout=60)
        logger.info(f"Client token request status: {resp.status_code}")
        
        if resp.status_code == 200:
            token_data = resp.json()
            if 'access_token' in token_data:
                logger.info("✓ Successfully obtained client token")
                return token_data['access_token']
            else:
                logger.error(f"Access token not found in response: {token_data}")
                # Try alternative response format
                if 'data' in token_data and 'access_token' in token_data['data']:
                    logger.info("Found access token in data field")
                    return token_data['data']['access_token']
        else:
            logger.error(f"Failed to get client token. Status: {resp.status_code}, Response: {resp.text[:200]}")
            
        return None
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout getting client token: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error getting client token: {e}")
        return None
    except Exception as e:
        logger.error(f"Exception in get_client_token: {e}")
        return None

def get_ei_token(session, client_token, phone_number):
    """Get encrypted ID token"""
    url = "https://api.sheinindia.in/uaas/accountCheck"
    
    headers = get_android_headers({
        'Authorization': f'Bearer {client_token}',
        'Requestid': 'account_check',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'api.sheinindia.in'
    })
    
    form_data = f'mobileNumber={phone_number}'
    
    try:
        resp = session.post(
            url, 
            data=form_data, 
            headers=headers, 
            timeout=30,
            params={
                'client_type': 'Android/29',
                'client_version': '8.5.1'
            }
        )
        
        logger.info(f"EI token status: {resp.status_code}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                logger.info(f"EI token response: {data}")
                
                # Try different possible response structures
                if 'encryptedId' in data:
                    ei = data['encryptedId']
                    logger.info(f"Found EI token in root: {ei}")
                    return ei
                elif 'data' in data and isinstance(data['data'], dict) and 'encryptedId' in data['data']:
                    ei = data['data']['encryptedId']
                    logger.info(f"Found EI token in data: {ei}")
                    return ei
                elif 'result' in data and isinstance(data['result'], dict) and 'encryptedId' in data['result']:
                    ei = data['result']['encryptedId']
                    logger.info(f"Found EI token in result: {ei}")
                    return ei
                else:
                    logger.error(f"EI token not found in response structure. Available keys: {data.keys() if isinstance(data, dict) else 'Not dict'}")
                    return ""
            except json.JSONDecodeError:
                logger.error("Failed to parse EI token JSON")
                return ""
        else:
            logger.error(f"EI token request failed: {resp.text}")
            return ""
            
    except Exception as e:
        logger.error(f"Exception in get_ei_token: {e}")
        return ""

def send_otp(session, c_token, mobile):
    """Send OTP to mobile number"""
    url = "https://api.sheinindia.in/uaas/login/sendOTP"
    
    headers = get_android_headers({
        'Authorization': f'Bearer {c_token}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'api.sheinindia.in'
    })
    
    form_data = f'mobileNumber={mobile}'
    
    try:
        resp = session.post(
            url, 
            data=form_data, 
            headers=headers, 
            timeout=30,
            params={
                'client_type': 'Android/29',
                'client_version': '8.5.1'
            }
        )
        
        logger.info(f"Send OTP status: {resp.status_code}")
        logger.info(f"Send OTP response: {resp.text}")
        
        if resp.status_code == 200:
            resp_data = resp.json()
            logger.info(f"OTP response data: {resp_data}")
            return True
        else:
            logger.error(f"Failed to send OTP: {resp.text}")
            return False
        
    except Exception as e:
        logger.error(f"Exception in send_otp: {e}")
        return False

def verify_otp_full(session, c_token, mobile, otp):
    """Verify OTP and get full authentication tokens"""
    url = "https://api.sheinindia.in/uaas/login/otp"
    
    headers = get_android_headers({
        'Authorization': f'Bearer {c_token}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'api.sheinindia.in'
    })
    
    # Build the form data with correct parameter names
    form_data = {
        'adId': AD_ID,
        'clientName': 'trusted_client',
        'expireOTP': 'true',
        'mobileNumber': mobile,
        'otp': otp,
        'clientSecret': 'secret',
        'grantType': 'password',
        'deviceId': str(uuid.uuid4()),
        'username': mobile
    }
    
    # URL encode the form data
    encoded_data = urllib.parse.urlencode(form_data)
    
    try:
        resp = session.post(
            url, 
            data=encoded_data, 
            headers=headers, 
            timeout=30,
            params={
                'client_type': 'Android/29',
                'client_version': '8.5.1'
            }
        )
        
        logger.info(f"OTP verify status: {resp.status_code}")
        logger.info(f"OTP verify response: {resp.text}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                logger.info(f"Auth data received. Keys: {list(data.keys()) if isinstance(data, dict) else 'Not dict'}")
                
                # Check if we have the required tokens
                if 'access_token' in data and 'refresh_token' in data:
                    logger.info("Successfully obtained auth tokens")
                    return data
                else:
                    logger.error(f"Missing required tokens in response: {data}")
                    return None
            except json.JSONDecodeError as je:
                logger.error(f"JSON decode error: {je}")
                logger.error(f"Response text: {resp.text}")
                return None
        else:
            logger.error(f"OTP verify failed with status {resp.status_code}: {resp.text}")
            return None
            
    except Exception as e:
        logger.error(f"Exception in verify_otp_full: {e}")
        return None

def fetch_profile_uid(session, access_token):
    """Fetch user profile UID"""
    url = "https://api.sheinindia.in/uaas/users/current"
    
    headers = get_android_headers({
        'Authorization': f'Bearer {access_token}',
        'Requestid': 'UserProfile',
        'Host': 'api.sheinindia.in'
    })
    
    try:
        resp = session.get(
            url, 
            headers=headers, 
            timeout=30,
            params={
                'client_type': 'Android/29',
                'client_version': '8.5.1'
            }
        )
        
        logger.info(f"Profile UID status: {resp.status_code}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                logger.info(f"Profile data: {data}")
                
                if 'uid' in data:
                    return data['uid']
                elif 'data' in data and isinstance(data['data'], dict) and 'uid' in data['data']:
                    return data['data']['uid']
                else:
                    logger.error(f"UID not found in profile: {data}")
                    return None
            except json.JSONDecodeError:
                logger.error("Failed to parse profile JSON")
                return None
        else:
            logger.error(f"Failed to fetch profile: {resp.text}")
            return None
            
    except Exception as e:
        logger.error(f"Exception in fetch_profile_uid: {e}")
        return None

def create_cookies_dict(mobile, auth_response, ei_value, uid_value):
    """Create cookies dictionary for authenticated session"""
    cookies = {
        'V': '1',
        '_fpuuid': str(uuid.uuid4()).replace('-', '')[:21],
        'deviceId': str(uuid.uuid4()),
        'storeTypes': 'shein',
        'LS': 'LOGGED_IN',
        'C': str(uuid.uuid4()),
        'EI': ei_value if ei_value else "",
        'A': auth_response.get('access_token', ''),
        'U': uid_value if uid_value else f"{mobile}@sheinindia.in",
        'R': auth_response.get('refresh_token', '')
    }
    
    logger.info(f"Created cookies. Keys: {list(cookies.keys())}")
    return cookies

# ---------------- Cart Functions ----------------
def extract_product_id_from_url(url_or_id):
    s = str(url_or_id)
    if s.isdigit():
        return s
    try:
        parsed = urllib.parse.urlparse(s)
        parts = parsed.path.strip("/").split("/")
        for seg in reversed(parts):
            if seg.isdigit():
                return seg
        m = re.search(r"(\d{6,})", s)
        if m:
            return m.group(1)
    except:
        pass
    return None

def ensure_cart_exists(cookies):
    r, data, ok = req("GET", URL_MICROCART, HEADERS_JSON, cookies, return_resp=True)
    if ok and data and data.get("code"):
        return data, cookies, None
    
    # Create new cart
    payload = {"user": urllib.parse.quote(USER_EMAIL).replace("%40", "%40"), "accessToken": ""}
    r, data, ok = req("POST", URL_CREATE, HEADERS_JSON, cookies, body=json.dumps(payload), return_resp=True)
    
    if not ok or data is None:
        return None, cookies, "create_cart failed"
    
    return data, cookies, None

def clear_cart_if_needed(cart_data, cookies):
    cart_id = cart_data.get("code")
    if not cart_id:
        return cart_data, "no cart id"
    
    body = {"entryNumber": 0}
    r, data, ok = req("POST", URL_DELETE, HEADERS_JSON, cookies, body=json.dumps(body), return_resp=True)
    
    if not ok or data is None:
        return None, "delete cart failed"
    
    return data, None

def check_serviceability(product_id, cookies):
    params = {"productCode": product_id, "postalCode": PINCODE, "quantity": "1", "IsExchange": "false"}
    r, data, ok = req("GET", URL_SERVICE_CHECK, HEADERS_JSON, cookies, params=params, return_resp=True)
    
    if not ok or data is None:
        return False, "service check failed"
    
    svc = data.get("servicability")
    details = data.get("productDetails") or [{}]
    svc_prod = details[0].get("servicability")
    
    return bool(svc and svc_prod), None

def add_item(cart_id, product_id_or_sku, cookies):
    url = URL_ADD_FMT.format(cart_id=cart_id, product_id=product_id_or_sku)
    body = {"quantity": 1}
    r, data, ok = req("POST", url, HEADERS_JSON, cookies, body=json.dumps(body), return_resp=True)
    
    if not ok or data is None:
        return False, f"add item failed: {getattr(r, 'status_code', 'no status')}"
    
    if isinstance(data, dict) and (data.get("statusCode") == "success" or data.get("status") == "success"):
        return True, None
    
    return False, "add failed"

def apply_voucher(voucher_code, cookies):
    payload = {"voucherId": voucher_code, "device": {"client_type": "MSITE"}}
    r, data, ok = req("POST", URL_APPLY_VOUCHER, HEADERS_JSON, cookies, body=json.dumps(payload), return_resp=True)
    
    if not ok or data is None:
        return None, "voucher apply failed"
    
    return data, None

# ---------------- Address Functions ----------------
def get_best_address(cookies):
    try:
        r = requests.get(URL_APP_ADDRESS, headers=HEADERS_JSON, cookies=cookies, timeout=30)
        if r.status_code >= 400:
            return None
        
        data = safe_json(r)
        if not data:
            return None
        
        # Try to extract address
        addr_list = None
        if isinstance(data, dict):
            for key in ("data", "addressList", "addresses", "result", "list"):
                if key in data:
                    candidate = data[key]
                    if isinstance(candidate, list):
                        addr_list = candidate
                        break
        
        if not addr_list or not isinstance(addr_list, list) or len(addr_list) == 0:
            return None
        
        # Return first address
        return addr_list[0]
    except:
        return None

# ---------------- Payment Functions ----------------
def build_banner_info_payload(cart_id, address_obj=None):
    user_info = {
        "email": USER_EMAIL,
        "phoneNumber": USER_MOBILE,
        "profileName": "",
        "userId": str(uuid.uuid4())
    }
    
    if address_obj:
        user_info["address"] = {
            "addressId": address_obj.get("id", ""),
            "consignee": address_obj.get("addressPoc", ""),
            "mobile": address_obj.get("phone", ""),
            "postalCode": address_obj.get("postalCode", ""),
            "country": "IN",
            "province": address_obj.get("state", ""),
            "city": address_obj.get("city", ""),
            "region": address_obj.get("district", ""),
            "address": address_obj.get("line1", "")
        }
    
    return {
        "item": {
            "baseRequest": {
                "consumerType": "STOREFRONT",
                "pageType": "string",
                "tenantId": "SHEIN",
                "cartId": cart_id,
                "channelInfo": {"appType": "OTHER", "channelType": "MSITE"},
                "userInfo": user_info
            }
        },
        "extraParam": {"addressId": address_obj.get("id", "") if address_obj else ""}
    }

def stage1_banner_info(cart_id, cookies, address_obj=None):
    if not address_obj:
        return None, "no address"
    
    try:
        payload = build_banner_info_payload(cart_id, address_obj)
        r, data, ok = req("POST", URL_BANNER_INFO, HEADERS_JSON, cookies, body=json.dumps(payload), return_resp=True)
        
        if not ok or data is None:
            return None, "banner info failed"
        
        return data, None
    except Exception as e:
        return None, f"stage1 exception: {e}"

def encode_stage2_body(stage1_json):
    parts = []
    for key, val in stage1_json.items():
        enc_key = urllib.parse.quote(f'"{key}"', safe="")
        if isinstance(val, (dict, list)):
            enc_val = urllib.parse.quote(json.dumps(val, separators=(",", ":")), safe="")
        elif isinstance(val, bool):
            enc_val = urllib.parse.quote(str(val).lower(), safe="")
        else:
            enc_val = urllib.parse.quote(str(val), safe="")
        parts.append(enc_key + "=" + enc_val)
    return "&".join(parts)

def stage2_pay(cart_id, stage1_json, cookies):
    body = encode_stage2_body(stage1_json)
    r, data, ok = req("POST", URL_PAY_STAGE2, {
        **COMMON_HEADERS,
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.sheinindia.in"
    }, cookies, body=body, allow_redirects=False, return_resp=True)
    
    if not (200 <= getattr(r, "status_code", 0) < 400):
        return None, "stage2 pay failed"
    
    return r, None

def build_pay_now_form(stage1_json, cookies=None):
    form_pairs = {
        "paymentInstrument": PAYMENT_METHOD,
        "notes[eligibleToEarnLoyalty]": "true",
        "paymentChannelInformation.paymentChannel": "MSITE",
        "paymentChannelInformation.appType": "OTHER",
        "tenant.code": "SHEIN",
        "tenant.callbackUrl": "https://www.sheinindia.in/payment-redirect",
        "tenantTransactionId": stage1_json.get("tenantTransactionId", ""),
        "customer.uuid": stage1_json.get("customer", {}).get("uuid", ""),
        "customer.email": USER_EMAIL,
        "customer.otp": "",
        "customer.mobile": USER_MOBILE,
        "order.orderId": stage1_json.get("order", {}).get("orderId", ""),
        "order.amount": str(stage1_json.get("order", {}).get("amount", "")),
        "order.netPayableAmount": str(stage1_json.get("order", {}).get("netAmount", "")),
        "order.totalPrice1p": str(stage1_json.get("order", {}).get("amount", "")),
        "order.totalPrice3p": "0",
        "accessToken": stage1_json.get("accessToken", ""),
        "requestChecksum": stage1_json.get("requestChecksum", ""),
        "deviceId": stage1_json.get("deviceId", ""),
        "deviceChecksum": stage1_json.get("deviceChecksum", ""),
        "cartCheckSum": stage1_json.get("cartCheckSum", ""),
        "transactionToken": stage1_json.get("transactionToken", "NA"),
    }
    return urllib.parse.urlencode(form_pairs)

def stage3_pay_now(cart_id, stage1_json, cookies):
    form_data = build_pay_now_form(stage1_json, cookies)
    r, data, ok = req("POST", URL_PAY_NOW, {
        **COMMON_HEADERS,
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://payment.sheinindia.in"
    }, cookies, body=form_data, allow_redirects=False, return_resp=True)
    
    html_text = getattr(r, "text", "")
    if not (200 <= getattr(r, "status_code", 0) < 400):
        return None, None, "pay now failed"
    
    return r, html_text, None

def parse_payment_success(html_text):
    if not html_text:
        return None
    
    # Try to find payment data
    m = re.search(r'name=["\']paymentEngineCallbackData["\']\s+value=["\']([^"\']+)["\']', html_text, re.I)
    if m:
        raw_val = m.group(1)
        try:
            candidate = html.unescape(raw_val)
            data = json.loads(candidate.replace('\\"', '"'))
        except:
            try:
                data = json.loads(raw_val.replace("'", '"'))
            except:
                data = None
        
        if data:
            tx_info = (data.get("transactionInformation") or {})
            order_info = (data.get("order") or {})
            status = tx_info.get("transactionStatus") or order_info.get("status") or data.get("status")
            order_id = order_info.get("orderId") or data.get("orderId")
            payable = order_info.get("netPayableAmount", order_info.get("amount") or data.get("amount"))
            return {"status": status, "order_id": order_id, "amount": payable}
    
    # Simple success detection
    if "SUCCESS" in html_text.upper():
        mo = re.search(r'order[_\s\-]?id[:=\s]*([A-Z0-9\-]{4,40})', html_text, re.I)
        order_id = mo.group(1) if mo else None
        return {"status": "SUCCESS", "order_id": order_id, "amount": None}
    
    return None

# ---------------- Watchlist Functions ----------------
def add_to_watch(chat_id, product_ref, voucher=""):
    pid = extract_product_id_from_url(product_ref) or product_ref
    if chat_id not in WATCHLIST:
        WATCHLIST[chat_id] = []
    
    for item in WATCHLIST[chat_id]:
        if item["product_id"] == pid:
            item["voucher"] = voucher
            return False
    
    WATCHLIST[chat_id].append({
        "product_id": pid,
        "ref": product_ref,
        "voucher": voucher,
        "active": True,
        "last_status": "added"
    })
    return True

def remove_from_watch(chat_id, product_ref):
    pid = extract_product_id_from_url(product_ref) or product_ref
    if chat_id not in WATCHLIST:
        return False
    
    for item in WATCHLIST[chat_id]:
        if item["product_id"] == pid:
            WATCHLIST[chat_id].remove(item)
            if not WATCHLIST[chat_id]:
                del WATCHLIST[chat_id]
            return True
    return False

def list_watch(chat_id):
    return WATCHLIST.get(chat_id, []).copy()

# ---------------- Monitor Loop ----------------
def monitor_loop():
    while MONITOR_RUNNING.is_set() and not BOT_STOPPED.is_set():
        for chat_id in list(WATCHLIST.keys()):
            if chat_id not in USER_SESSIONS:
                continue
            
            user_data = USER_SESSIONS[chat_id]
            if "cookies" not in user_data:
                continue
            
            cookies = user_data["cookies"]
            watchlist = WATCHLIST.get(chat_id, [])
            
            for item in watchlist:
                if not item.get("active", True) or BOT_STOPPED.is_set():
                    continue
                
                try:
                    pid = item["product_id"]
                    
                    # Ensure cart
                    cart_data, _, err = ensure_cart_exists(cookies)
                    if err:
                        tg_send(chat_id, f"⚠ Cart error: {err}")
                        continue
                    
                    # Clear cart
                    cart_data, err = clear_cart_if_needed(cart_data, cookies)
                    if err:
                        tg_send(chat_id, f"⚠ Clear cart error: {err}")
                        continue
                    
                    # Check serviceability
                    ok, svc_err = check_serviceability(pid, cookies)
                    if not ok:
                        item["last_status"] = "not serviceable"
                        continue
                    
                    cart_live, _, err = ensure_cart_exists(cookies)
                    if err:
                        continue
                    
                    cart_id = cart_live.get("code")
                    if not cart_id:
                        continue
                    
                    # Add item
                    added, add_err = add_item(cart_id, pid, cookies)
                    if not added:
                        item["last_status"] = f"add failed: {add_err}"
                        continue
                    
                    # Apply voucher
                    voucher = item.get("voucher", "")
                    if voucher:
                        apply_voucher(voucher, cookies)
                    
                    # Get address
                    address_obj = get_best_address(cookies)
                    if not address_obj:
                        tg_send(chat_id, "⚠ No address found")
                        continue
                    
                    # Stage 1
                    stage1_json, s1_err = stage1_banner_info(cart_id, cookies, address_obj)
                    if s1_err:
                        tg_send(chat_id, f"⚠ Stage1 failed: {s1_err}")
                        continue
                    
                    # Stage 2
                    _, s2_err = stage2_pay(cart_id, stage1_json, cookies)
                    if s2_err:
                        tg_send(chat_id, f"⚠ Stage2 failed: {s2_err}")
                        continue
                    
                    # Stage 3
                    r3, html_text, s3_err = stage3_pay_now(cart_id, stage1_json, cookies)
                    if s3_err:
                        tg_send(chat_id, f"⚠ Pay now failed: {s3_err}")
                        continue
                    
                    # Parse result
                    parsed = parse_payment_success(html_text)
                    if parsed:
                        status = (parsed.get("status") or "").upper()
                        if status == "SUCCESS":
                            tg_send(chat_id, f"✅ Order placed! ID: {parsed.get('order_id')}")
                            item["active"] = False
                        elif status in ("PENDING", "INITIATED"):
                            tg_send(chat_id, f"⏳ Payment pending. Check UPI app.")
                        else:
                            tg_send(chat_id, f"❌ Payment failed: {status}")
                    
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                
                time.sleep(CHECK_INTERVAL_SECONDS)
        
        time.sleep(MONITOR_LOOP_SLEEP)

# ---------------- Telegram Commands ----------------
@bot.message_handler(commands=['start', 'help'])
def cmd_start(m):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    if m.chat.id in USER_SESSIONS and "cookies" in USER_SESSIONS[m.chat.id]:
        markup.add(types.KeyboardButton('🚀 Auto Order'), types.KeyboardButton('📦 Add Product'))
        markup.add(types.KeyboardButton('📋 Watchlist'), types.KeyboardButton('⏸️ Stop Monitor'))
        markup.add(types.KeyboardButton('🔓 Logout'))
    else:
        markup.add(types.KeyboardButton('🔐 Login'))
    
    welcome = (
        "✨ **Shein Auto-Buyer** ✨\n\n"
        "Features:\n"
        "• 🔐 Mobile number login\n"
        "• 🚀 Auto order placement\n"
        "• 📦 Multiple product monitoring\n"
        "• 🎟 Voucher support\n"
        "• 💳 UPI payments\n\n"
        "Use buttons below to get started!"
    )
    bot.reply_to(m, welcome, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == '🔐 Login')
def handle_login(m):
    if m.chat.id in USER_SESSIONS and "cookies" in USER_SESSIONS[m.chat.id]:
        bot.send_message(m.chat.id, "✅ Already logged in!")
        return
    
    # Test connection first
    bot.send_message(m.chat.id, "🔍 Testing connection to Shein servers...")
    if not test_connection():
        bot.send_message(m.chat.id, 
            "❌ **Connection Failed!**\n\n"
            "Cannot connect to Shein servers. Possible reasons:\n"
            "1. 🚫 Internet connection issue\n"
            "2. 🌐 DNS resolution problem\n"
            "3. 🛡️ Firewall/Proxy blocking\n"
            "4. ⚠️ Shein server down\n\n"
            "Please check your network and try again.")
        return
    
    USER_SESSIONS[m.chat.id] = {'step': 'waiting_for_mobile'}
    bot.send_message(m.chat.id, "📱 Enter your 10-digit mobile number:")

@bot.message_handler(func=lambda msg: USER_SESSIONS.get(msg.chat.id, {}).get('step') == 'waiting_for_mobile')
def handle_mobile(m):
    mobile = m.text.strip()
    if not mobile.isdigit() or len(mobile) != 10:
        bot.send_message(m.chat.id, "❌ Invalid number. Enter 10-digit mobile:")
        return
    
    # Create a new session for this user
    session = make_session_with_retries()
    
    USER_SESSIONS[m.chat.id] = {
        'step': 'waiting_for_otp',
        'mobile': mobile,
        'session': session
    }
    
    try:
        bot.send_message(m.chat.id, f"⏳ Getting client token for {mobile}...")
        c_token = get_client_token(session)
        
        if not c_token:
            bot.send_message(m.chat.id, 
                "❌ **Failed to get client token!**\n\n"
                "Possible issues:\n"
                "1. ⏱️ Server timeout\n"
                "2. 🔒 Shein API changed\n"
                "3. 🌐 Network issue\n\n"
                "Please try again in a few minutes.")
            del USER_SESSIONS[m.chat.id]
            return
        
        bot.send_message(m.chat.id, "⏳ Sending OTP...")
        if send_otp(session, c_token, mobile):
            USER_SESSIONS[m.chat.id]['c_token'] = c_token
            bot.send_message(m.chat.id, f"✅ OTP sent to {mobile}. Enter 4-digit OTP:")
        else:
            bot.send_message(m.chat.id, "❌ Failed to send OTP. Please try again.")
            del USER_SESSIONS[m.chat.id]
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        bot.send_message(m.chat.id, f"❌ Error during login: {str(e)}")
        del USER_SESSIONS[m.chat.id]

@bot.message_handler(func=lambda msg: USER_SESSIONS.get(msg.chat.id, {}).get('step') == 'waiting_for_otp')
def handle_otp(m):
    otp = m.text.strip()
    if not otp.isdigit() or len(otp) != 4:
        bot.send_message(m.chat.id, "❌ Invalid OTP. Enter 4-digit OTP:")
        return
    
    user_data = USER_SESSIONS[m.chat.id]
    mobile = user_data['mobile']
    session = user_data['session']
    c_token = user_data['c_token']
    
    try:
        bot.send_message(m.chat.id, "⏳ Verifying OTP...")
        auth_data = verify_otp_full(session, c_token, mobile, otp)
        
        if auth_data:
            bot.send_message(m.chat.id, "⏳ Getting encrypted ID...")
            ei_value = get_ei_token(session, c_token, mobile)
            
            bot.send_message(m.chat.id, "⏳ Fetching user profile...")
            acc_token = auth_data.get('access_token')
            uid_from_api = fetch_profile_uid(session, acc_token)
            
            # Create cookies for web session
            cookies = create_cookies_dict(mobile, auth_data, ei_value, uid_from_api)
            
            # Store user data
            USER_SESSIONS[m.chat.id] = {
                'cookies': cookies,
                'mobile': mobile,
                'uid': uid_from_api,
                'session': session  # Keep the session for future API calls
            }
            
            markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            markup.add(types.KeyboardButton('🚀 Auto Order'), types.KeyboardButton('📦 Add Product'))
            markup.add(types.KeyboardButton('📋 Watchlist'), types.KeyboardButton('⏸️ Stop Monitor'))
            markup.add(types.KeyboardButton('🔓 Logout'))
            
            success_msg = (
                f"✅ **Login Successful!**\n\n"
                f"📱 Account: `{mobile}`\n"
                f"🆔 UID: `{uid_from_api if uid_from_api else 'Not found'}`\n"
                f"🔐 EI Token: `{'Yes' if ei_value else 'No'}`\n\n"
                f"Now you can start auto-ordering!"
            )
            bot.send_message(m.chat.id, success_msg, reply_markup=markup, parse_mode="Markdown")
            
            # Test the session
            bot.send_message(m.chat.id, "⏳ Testing session...")
            try:
                cart_test, _, err = ensure_cart_exists(cookies)
                if err:
                    bot.send_message(m.chat.id, f"⚠ Cart test failed: {err}")
                else:
                    bot.send_message(m.chat.id, "✅ Session test successful!")
            except Exception as e:
                bot.send_message(m.chat.id, f"⚠ Session test error: {e}")
                
        else:
            bot.send_message(m.chat.id, "❌ Invalid OTP or authentication failed. Please try /start again")
            del USER_SESSIONS[m.chat.id]
            
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        bot.send_message(m.chat.id, f"❌ Error during OTP verification: {str(e)}")
        del USER_SESSIONS[m.chat.id]

@bot.message_handler(func=lambda msg: msg.text == '🔓 Logout')
def handle_logout(m):
    if m.chat.id in USER_SESSIONS:
        mobile = USER_SESSIONS[m.chat.id].get('mobile', 'Unknown')
        del USER_SESSIONS[m.chat.id]
        if m.chat.id in WATCHLIST:
            del WATCHLIST[m.chat.id]
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton('🔐 Login'))
        
        bot.send_message(m.chat.id, 
            f"✅ **Logged out!**\n"
            f"📱 Account: {mobile}\n\n"
            f"You can login with another number.",
            reply_markup=markup)
    else:
        bot.send_message(m.chat.id, "❌ Not logged in!")

@bot.message_handler(func=lambda msg: msg.text == '📦 Add Product')
def handle_add_product(m):
    if m.chat.id not in USER_SESSIONS or "cookies" not in USER_SESSIONS[m.chat.id]:
        bot.send_message(m.chat.id, "❌ Please login first!")
        return
    
    USER_SESSIONS[m.chat.id]['step'] = 'waiting_for_product'
    bot.send_message(m.chat.id, 
        "📦 **Add Product to Watchlist**\n\n"
        "Send:\n"
        "1. Product URL (shein link)\n"
        "2. Product ID (6+ digits)\n\n"
        "Optional: Add voucher code after space\n"
        "Example: `https://shein... VOUCHER123`")

@bot.message_handler(func=lambda msg: USER_SESSIONS.get(msg.chat.id, {}).get('step') == 'waiting_for_product')
def handle_product_input(m):
    parts = m.text.split(maxsplit=1)
    product_ref = parts[0].strip()
    voucher = parts[1].strip() if len(parts) > 1 else ""
    
    pid = extract_product_id_from_url(product_ref)
    if not pid:
        bot.send_message(m.chat.id, "❌ Invalid product. Try again:")
        return
    
    added = add_to_watch(m.chat.id, product_ref, voucher)
    
    if added:
        bot.send_message(m.chat.id, f"✅ Added to watchlist!\nID: `{pid}`\nVoucher: `{voucher}`", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, f"✅ Updated watchlist entry!")
    
    USER_SESSIONS[m.chat.id].pop('step', None)

@bot.message_handler(func=lambda msg: msg.text == '📋 Watchlist')
def handle_watchlist(m):
    if m.chat.id not in WATCHLIST or not WATCHLIST[m.chat.id]:
        bot.send_message(m.chat.id, "📭 Watchlist is empty!")
        return
    
    items = WATCHLIST[m.chat.id]
    msg = "📋 **Your Watchlist**\n\n"
    
    for i, item in enumerate(items, 1):
        msg += (
            f"{i}. 🆔 `{item['product_id']}`\n"
            f"   🔗 {item['ref'][:50]}...\n"
            f"   🎟 Voucher: `{item.get('voucher', 'None')}`\n"
            f"   ⚡ Active: `{item.get('active', True)}`\n"
            f"   📝 Status: {item.get('last_status', 'N/A')}\n\n"
        )
    
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == '🚀 Auto Order')
def handle_auto_order(m):
    if m.chat.id not in USER_SESSIONS or "cookies" not in USER_SESSIONS[m.chat.id]:
        bot.send_message(m.chat.id, "❌ Please login first!")
        return
    
    if m.chat.id not in WATCHLIST or not WATCHLIST[m.chat.id]:
        bot.send_message(m.chat.id, "❌ Add products to watchlist first!")
        return
    
    if MONITOR_RUNNING.is_set():
        bot.send_message(m.chat.id, "⚠️ Monitor already running!")
        return
    
    MONITOR_RUNNING.set()
    threading.Thread(target=monitor_loop, daemon=True).start()
    bot.send_message(m.chat.id, "🚀 **Auto-order started!**\nMonitoring products...")

@bot.message_handler(func=lambda msg: msg.text == '⏸️ Stop Monitor')
def handle_stop_monitor(m):
    if not MONITOR_RUNNING.is_set():
        bot.send_message(m.chat.id, "⚠️ Monitor not running!")
        return
    
    MONITOR_RUNNING.clear()
    bot.send_message(m.chat.id, "⏸️ **Monitor stopped!**")

@bot.message_handler(commands=['test_connection'])
def cmd_test_connection(m):
    """Test connection to Shein servers"""
    bot.send_message(m.chat.id, "🔍 Testing connection to Shein servers...")
    
    if test_connection():
        bot.send_message(m.chat.id, "✅ **Connection Successful!**\nAll Shein servers are reachable.")
    else:
        bot.send_message(m.chat.id, 
            "❌ **Connection Failed!**\n\n"
            "Troubleshooting steps:\n"
            "1. 🌐 Check your internet connection\n"
            "2. 🔄 Restart the bot\n"
            "3. 🖥️ Try from a different network\n"
            "4. ⏰ Wait and try again later")

@bot.message_handler(commands=['status'])
def cmd_status(m):
    if m.chat.id not in USER_SESSIONS:
        bot.send_message(m.chat.id, "❌ Not logged in!")
        return
    
    user_data = USER_SESSIONS[m.chat.id]
    mobile = user_data.get('mobile', 'N/A')
    uid = user_data.get('uid', 'N/A')
    has_cookies = 'cookies' in user_data
    monitor_on = MONITOR_RUNNING.is_set()
    watch_count = len(WATCHLIST.get(m.chat.id, []))
    
    msg = (
        f"📊 **Account Status**\n\n"
        f"📱 Mobile: `{mobile}`\n"
        f"🆔 UID: `{uid}`\n"
        f"🔐 Logged in: `{has_cookies}`\n"
        f"🚀 Monitor: `{'Running' if monitor_on else 'Stopped'}`\n"
        f"📦 Watchlist items: `{watch_count}`\n"
        f"💳 Payment method: `{PAYMENT_METHOD}`"
    )
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['test'])
def cmd_test(m):
    if m.chat.id not in USER_SESSIONS or "cookies" not in USER_SESSIONS[m.chat.id]:
        bot.send_message(m.chat.id, "❌ Please login first!")
        return
    
    try:
        cookies = USER_SESSIONS[m.chat.id]['cookies']
        cart_data, _, err = ensure_cart_exists(cookies)
        if err:
            bot.send_message(m.chat.id, f"❌ Cart test failed: {err}")
            return
        
        address = get_best_address(cookies)
        if address:
            bot.send_message(m.chat.id, f"✅ Test passed!\nCart: OK\nAddress: Found")
        else:
            bot.send_message(m.chat.id, "⚠️ Test passed but no address found")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ Test failed: {e}")

@bot.message_handler(commands=['stopbot'])
def cmd_stopbot(m):
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.send_message(m.chat.id, "❌ Admin only command!")
        return
    
    bot.send_message(m.chat.id, "🛑 Stopping bot...")
    BOT_STOPPED.set()
    MONITOR_RUNNING.clear()
    bot.stop_polling()

# ---------------- Main ----------------
def run_bot():
    logger.info("Starting Shein Auto-Buyer Bot...")
    
    # Test connection at startup
    logger.info("Testing initial connection to Shein servers...")
    if not test_connection():
        logger.warning("Initial connection test failed. Bot may not work properly.")
    
    # Clear any existing webhook first
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        logger.info("Cleared existing webhook")
    except:
        pass
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
    finally:
        MONITOR_RUNNING.clear()
        BOT_STOPPED.set()
        logger.info("Bot stopped")

if __name__ == "__main__":
    # Use a single-instance lock (bind to localhost port) instead of killing processes.
    LOCK_PORT = int(os.environ.get("ORDERR_LOCK_PORT", "52341"))
    lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lock_sock.bind(("127.0.0.1", LOCK_PORT))
        lock_sock.listen(1)
        logger.info("Acquired instance lock on port %s", LOCK_PORT)
    except OSError:
        logger.error("Another instance appears to be running (could not acquire lock on port %s). Exiting.", LOCK_PORT)
        sys.exit(1)

    try:
        run_bot()
    finally:
        try:
            lock_sock.close()
        except Exception:
            pass
