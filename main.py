import discord
from discord.ext import commands
from discord import app_commands
import logging
from dotenv import load_dotenv
import os
import json

def load_all_configs():
    """Reads the JSON file. Returns an empty dict if the file doesn't exist."""
    if not os.path.exists("config.json"):
        return {}
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_config(guild_id, hub_id, cat_id):
    """Updates the JSON file with new IDs for a specific server."""
    data = load_all_configs()
    # We use str(guild_id) because JSON keys must be strings
    data[str(guild_id)] = {
        "hub_id": hub_id, 
        "cat_id": cat_id
    }
    with open("config.json", "w") as f:
        json.dump(data, f, indent=4)

# Getting Discord Token
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Creating a Log/Console File
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

# Discord bot Intents(Permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True  # Required to detect VC joins/leaves
intents.guilds = True        # Required to manage channels

# Bot command prefix
bot = commands.Bot(command_prefix="/", intents=intents)

# Tracking created channels
temp_channels = []

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Commands synced!")
    print(f'Logged in as {bot.user.name}')

# /setup command
@bot.tree.command(name="setup", description="Set the Hub channel and Category for temporary VCs")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    guild = interaction.guild
    category_name = "Temporary Channels"
    hub_name = "➕ Join to Create"

    # 1. Check if the Category exists
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
        status_cat = f"✅ Created Category: **{category_name}**"
    else:
        status_cat = f"ℹ️ Category **{category_name}** already exists."

    # 2. Check if the Hub Channel exists inside that category
    hub_channel = discord.utils.get(category.voice_channels, name=hub_name)
    if hub_channel is None:
        hub_channel = await guild.create_voice_channel(hub_name, category=category)
        status_hub = f"✅ Created Hub: **{hub_name}**"
    else:
        status_hub = f"ℹ️ Hub **{hub_name}** already exists."

    # Final report to the user
    await interaction.response.send_message(f"{status_cat}\n{status_hub}", ephemeral=True)

    # Saving to a config file
    try:
        save_config(guild.id, hub_channel.id, category.id)
        await interaction.response.send_message(
            f"✅ System ready and saved!\n**Category ID:** `{category.id}`\n**Hub ID:** `{hub_channel.id}`", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to save config: {e}", ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    # 1. Loading Category and Hub ID
    configs = load_all_configs()

    # We convert the ID to a string because JSON keys are always strings
    guild_id = str(member.guild.id)
    guild_data = configs.get(guild_id)

    # check if setup is done
    if not guild_data:
        return
    
    # passing IDs
    hub_id = guild_data.get("hub_id")
    cat_id = guild_data.get("cat_id")

    # 2. Check if user joined the "Join to Create" Hub
    if after.channel and after.channel.id == hub_id:
        guild = member.guild
        category = guild.get_channel(cat_id)

        # Create the new voice channel
        new_channel = await guild.create_voice_channel(
            name=f"{member.display_name}'s Room",
            category=category
        )

        # Move the member to the new channel
        await member.move_to(new_channel)
        
        # Add to our tracking list
        temp_channels.append(new_channel.id)

    # 3. Cleanup: Check if the channel the user left was a temp channel
    if before.channel and before.channel.id in temp_channels:
        # If the channel is now empty, delete it
        if len(before.channel.members) == 0:
            await before.channel.delete()
            temp_channels.remove(before.channel.id)


# Running the Bot
bot.run(token, log_handler=handler, log_level=logging.DEBUG)