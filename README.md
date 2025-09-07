# 🚀 Sixpence Bot - Automation for Sixpence AI

## 📢 Connect with Us

- **📢 Channel**: [https://t.me/D3_vin](https://t.me/D3_vin) - Latest updates and releases
- **💬 Chat**: [https://t.me/D3vin_chat](https://t.me/D3vin_chat) - Community support and discussions
- **📁 GitHub**: [https://github.com/D3-vin](https://github.com/D3-vin) - Source code and development

## ✨ Key Features

- 🔐 **Automatic Registration** - bulk account registration with referral codes
- 🌾 **Smart Farming** - automatic point collection through WebSocket connections
- 🔄 **Proxy Rotation** - automatic proxy switching on connection errors
- 📊 **Multi-threading** - separate thread settings for registration and farming
- 💾 **Database** - automatic saving of tokens and referral codes
- 🔧 **Flexible Settings** - complete configuration through config file
- 📝 **Detailed Logging** - configurable logging levels (DEBUG, INFO, WARNING, ERROR)
- 🛡️ **Fault Tolerance** - automatic retries with smart delay logic

## 🚀 Advantages

- ✅ **Simplified Structure** - logical code organization without unnecessary nesting
- ✅ **Modular Architecture** - clear separation of API, Core, Data, UI, Utils
- ✅ **Automatic Management** - state saving, session recovery
- ✅ **Advanced Error Handling** - smart retries with exponential delays
- ✅ **WebSocket Authentication** - automatic saving and reuse of auth messages
- ✅ **Referral System** - automatic reuse of codes from database

## 📁 Project Structure

```
sixpence/
├── main.py                 # 🎯 Main entry point
├── requirements.txt        # 📦 Python dependencies
├── README.md              # 📖 Documentation
├── config/               # 📋 Configuration files
│   ├── config.yaml      # Main settings
│   └── data/            # Data files
│       ├── reg.txt      # Keys for registration
│       ├── farm.txt     # Keys for farming
│       └── proxy.txt    # Proxy list
│
├── data/                # 💾 Runtime data
│   └── sixpence.db     # SQLite database
│
└── logs/               # 📋 Log files
    └── sixpence.log    # Main log file
```

## 🛠️ Installation and Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Data Files

**Add private keys:**
- `config/data/reg.txt` - private keys for registration (one per line)
- `config/data/farm.txt` - private keys for farming (one per line)

**Add proxies (optional):**
- `config/data/proxy.txt` - proxy list in format `http://user:pass@ip:port`

### 3. Configuration Setup

Edit `config/config.yaml`:

```yaml
# Multi-threading
threads:
  registration: 5  # Threads for registration
  farming: 3       # Threads for farming

# Logging
logging:
  level: "INFO"    # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Referral codes
sixpence_ref_code: "YOUR_REF_CODE"
use_static_ref_code: false  # true = static code, false = random from DB

# Delays
delay_before_start:
  min: 1
  max: 3

# Retry settings
retry:
  max_attempts: 3           # Maximum connection attempts
  delay_seconds: 5          # Delay between attempts
  farming_wait_seconds: 6   # Delay after exhausting attempts
  proxy_rotation: true      # Enable proxy rotation
```

## 🎮 Launch

```bash
python main.py
```

### Operations Menu:
1. **Registration** - Automatic account registration
2. **Farming** - Start farming process
3. **Exit** - Exit the program

## 📊 System Features

### 🔄 Smart Proxy Rotation
- Automatic proxy switching after exhausting connection attempts
- Configurable number of attempts per proxy
- Option to disable rotation for single proxy work

### 🌾 Intelligent Farming
- Automatic reuse of WebSocket auth messages
- Graceful reconnection on connection loss
- State saving in database

### 🔐 Authentication System
- Automatic token saving and updating
- Caching of signed messages for WebSocket
- Automatic re-authentication on token expiration

### 📈 Referral System
- Automatic retrieval and saving of referral codes
- Code reuse between accounts
- Support for static and dynamic referral codes

## 🔍 Monitoring and Logging

### Log Files
- **Console:** Colored logs in real-time
- **File:** `logs/sixpence.log` with daily rotation
- **Levels:** DEBUG, INFO, SUCCESS, WARNING, ERROR

This tool is for educational and testing purposes on testnets only. Always verify transactions and use at your own risk.