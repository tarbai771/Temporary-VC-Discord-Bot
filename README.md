# Temporary-VC-Discord-Bot
This is a Discord Bot that gives regular users to create and manage their own voice channels using a button based interface. This codebase is free open source for anybody to copy, distribute, change or use for their own bot according to their personal server needs.

---
## ✨Features

- **Dynamic Privacy:** Toggle between **Locked**, **Invisible**, or **Closed** states using a single dropdown.
    
- **Trust System:** Grant specific users "VIP access" to bypass locks and chat restrictions.
    
- **Interactive Invites:** Send "Drag-to-VC" invites with Accept/Reject buttons.
    
- **User Management:** Kick, Block, or Transfer ownership of the room effortlessly.
    
- **Clean UI:** Uses Discord's modern `ui.View` components (Buttons and Select Menus) to keep chat clutter-free.


---
## Trust System
It allows voice channel creator to add users into trusted user list. which allows trusted users to join voice channel even if your voice channel is locked 

---
##  Privacy Modes Explained

| **Mode**         | **Effect**                                            |
| ---------------- | ----------------------------------------------------- |
| **Lock Room**    | Allows only trusted users to join.                    |
| **Invisible**    | Hides the channel from everyone except Trusted users. |
| **Disable Chat** | Mutes the text channel for everyone (Strict Mode).    |
| **Close Chat**   | Only the Owner and Trusted users can type.            |

---
### 🛠️ Installation & Setup

1. **Clone the repository:**
```
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

2. **Create a Virtual Environment:**
```
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

3. **Install Dependencies:**
```
pip install discord.py
```

4. **Configure your Token:** Create a `.env` file or replace the token variable in `main.py` with your bot's token from the [Discord Developer Portal](https://www.google.com/search?q=https://discord.com/developers/applications).
 
5. **Run the Bot:**
```
python main.py
```

---
### 📜 Requirements

- `python 3.10+`
- `discord.py 2.0+`
- `python-dotenv`
- **Bot Intentions:** Ensure `Members` and `Message Content` intents are enabled in your developer portal.

#### 🛠️ One-Step Installation
Users can install all dependencies at once by running:
```
pip install -r requirements.txt
```

---
## 📜License
**MIT License**
