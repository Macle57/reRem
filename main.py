
import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
import asyncio
import os
import datetime
import dateutil.parser
# importing necessary functions from dotenv library
from dotenv import load_dotenv, dotenv_values 
# loading variables from .env file
load_dotenv() 

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.members = True  # Enable member intents (important for accessing member list)

# Create a bot instance with a specified command prefix, e.g., '!'
bot = commands.Bot(command_prefix='/', intents=intents)

def print_GCs_results(results):
    for item in results:
        channel = item['channel']
        roles = item['role']
        # Prepare role names for display
        role_names = ', '.join(role.name for role in roles) if roles else 'No matching roles'
        print(f"Channel Name: {channel.category} {channel.name} - Accessible by: {role_names}")

def format_GCs_results(results):
    response_lines = []
    max_length = 1900  # Set a maximum length to leave room for additional characters
    for item in results:
        channel = item['channel']
        roles = item['role']
        # Prepare role names for display
        role_names = ', '.join(role.name for role in roles) if roles else 'No matching roles'
        # Format for Discord output
        line = f"**{channel.category if channel.category else 'No Category'} {channel.name}** - Accessible by: {role_names}"
        if len("\n".join(response_lines)) + len(line) > max_length:
            response_lines.append("...and more")
            break
        response_lines.append(line)
    return "\n".join(response_lines)


def get_mentions_asid(pings_string):
    # Regular expression to find content between <@& and >
    pattern = r"<@&([^>]*)>"
    print(re.findall(pattern, pings_string))
    # Find all matches of the pattern
    return [int(role) for role in re.findall(pattern, pings_string)]



def get_GCs(guild, search_string='-group-chat'):
    # Sort by category name first (None if no category), then by extracted number
    sortKey = lambda channel: (channel.category.name if channel.category else 'ZZZ', int(re.search(r'-(\d+)-', channel.name).group(1)))
    
    matching_channels: list[discord.TextChannel] = sorted([channel for channel in guild.channels if search_string.lower() in channel.name.lower()],
                               key=sortKey)
    result = []
    for channel in matching_channels:
        # Extract number from channel name
        channel_number = re.search(r'-(\d+)-', channel.name).group(1)
        # Create a regex pattern that matches 'team' followed anywhere by the number
        pattern = re.compile(r'team.*' + re.escape(channel_number), re.IGNORECASE)
        
        # Filter roles that match the regex pattern
        valid_roles = [role for role in channel.overwrites.keys() if isinstance(role, discord.Role) and 
                       pattern.search(role.name)]
        
        result.append({"channel": channel, "role": valid_roles if valid_roles else []})
    # print_GCs_results(result)
    return result

async def send_message_to_channel(channel, message):
    """Send a message to a specific channel."""
    try:
        await channel.send(message)
    except discord.Forbidden:
        print(f"Failed to send message to {channel.name}, permission denied.")
    except discord.HTTPException as e:
        print(f"HTTP error occurred: {e}")


async def send_message(member, message):
    try:
        await member.send(message)
        logger.info(f"Message sent to: {member.name}")
    except discord.Forbidden:
        logger.error(f"Could not send message to {member.name}: Forbidden.")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced: {len(synced)} command(s)")
    except Exception as e:
        print(e)


# Test ping command
@bot.tree.command(name='ping')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"{round(bot.latency * 1000)}ms {interaction.user.mention}!")


# send dm to each member with the specified roles with a message, doesnt accept user mentions, only role mentions
@bot.tree.command(name='senddmbyrole')
@app_commands.describe(message='The message to be sent to each role Member', rolesstring='Enter as many roles as you wish to DM')
async def senddmbyrole(interaction: discord.Interaction, message: str, rolesstring: str):
    """ Sends a DM to all members with the specified roles. """
    guild = interaction.guild  # Use the guild from where the command was invoked
    if guild is None:
        await interaction.response.send_message("Command must be used within a server.")
        return
    roles = [discord.utils.get(guild.roles, id=role) for role in get_mentions_asid(rolesstring)]
    if any(role is None for role in roles):
        await interaction.send(f"One or more roles not found.")
        return

    members = set()  # Use a set to avoid duplicate members

    for role in roles:
        for member in role.members:
            members.add(member)

    tasks = [send_message(member, message) for member in members]
    await asyncio.gather(*tasks)
    await interaction.response.send_message(f"Message sent to {len(members)} members.")


# send dm to each member with the specified users with a message, doesnt accept role mentions, only user mentions
@bot.tree.command(name='senddm')
@app_commands.describe(message='The message to be sent to each member', usersstring='Enter as many users as you wish to DM')
async def senddm(interaction: discord.Interaction, message: str, usersstring: str):
    # Sends a DM to all specified users
    guild = interaction.guild  # Use the guild from where the command was invoked
    if guild is None:
        await interaction.response.send_message("Command must be used within a server.")
        return
    print(usersstring)
    users = [discord.utils.get(guild.members, id=user) for user in get_mentions_asid(usersstring)]
    if any(user is None for user in users):
        await interaction.send(f"One or more users not found.")
        return

    tasks = [send_message(user, message) for user in users]
    for taskCluster in range(0, len(tasks), 3):
        await asyncio.gather(*tasks[taskCluster:taskCluster+3])
    await interaction.response.send_message(f"Message sent to {len(users)} members.")



@bot.tree.command(name='verifyroles', description='Verify each role against the channel name.')
async def verifyroles(interaction: discord.Interaction):
    """Search for channels that contain a specific string in their name."""
    guild = interaction.guild
    if guild:
        results = get_GCs(guild)
        response = format_GCs_results(results)
        if not response:
            response = "No channels found or no roles match your criteria."
        await interaction.response.send_message(response)

class CancelView(discord.ui.View):
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel_button")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # This method will be called when the "Cancel" button is clicked
        await interaction.response.send_message("Operation cancelled!", ephemeral=True)
        self.stop()  # Stop the view to prevent further interactions

@bot.tree.command(name='set_reminder', description='Set a reminder to send messages to channels.')
async def set_reminder(interaction: discord.Interaction, reminder_time: str, reminder_message: str):
    """Set a reminder to send a message to all channels with '-group-chat' in their names at the specified time."""
    reminder_dt = dateutil.parser.parse(reminder_time)
    delay = (reminder_dt - datetime.datetime.now()).total_seconds()

    hours, remainder = divmod(delay, 3600)
    minutes = remainder // 60
    await interaction.response.send_message(f"Reminder set for {int(hours)} hours and {int(minutes)} minutes from now.", view=CancelView())

    # Sleep until the specified time
    await asyncio.sleep(delay)
    results = get_GCs(interaction.guild)

    # Gather tasks for sending messages
    tasks = [send_message_to_channel(item['channel'], reminder_message + f'<@&{item['role'][0].id}>') for item in results]
    for taskCluster in range(0, len(tasks), 5):
        await asyncio.gather(*tasks[taskCluster:taskCluster+5])

    await interaction.followup.send(f"Reminder message sent to {len(results)} channels.")



# # returns all channels in given category with given name
# def getAllGCs(guild):



bot.run(os.getenv('DISCORD_TOKEN'))
