import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
import asyncio
import os
import datetime
import dateutil.parser
import dateutil.tz # Added for timezone handling
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

# --- Helper Functions (print_GCs_results, format_GCs_results, get_mentions_asid, get_GCs, send_message_to_channel, send_message) ---
# Assume these functions remain the same as in your original code
# ... (Paste your existing helper functions here) ...
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

# --- FIX NEEDED for senddm ---
# This regex is for USER mentions (<@id> or <@!id>)
user_mention_pattern = r"<@!?(\d+)>"
def get_user_mentions_asid(pings_string):
    return [int(user_id) for user_id in re.findall(user_mention_pattern, pings_string)]
# --- End FIX ---


def get_GCs(guild, search_string='-group-chat'):
    # Sort by category name first (None if no category), then by extracted number
    def sortKey(channel):
        try:
            # Use category name (or a high value string if no category)
            cat_name = channel.category.name if channel.category else '~~~ZZZ' # Sort no-category last
            # Extract number, handle potential errors if pattern not found
            match = re.search(r'-(\d+)-', channel.name)
            num = int(match.group(1)) if match else float('inf') # Sort channels without number last
            return (cat_name, num)
        except Exception as e:
            logger.error(f"Error sorting channel {channel.name}: {e}")
            return ('~~~ZZZ', float('inf')) # Fallback sorting

    matching_channels: list[discord.TextChannel] = []
    if guild and guild.channels:
        matching_channels = sorted(
            [channel for channel in guild.channels
             if isinstance(channel, discord.TextChannel) and search_string.lower() in channel.name.lower()],
            key=sortKey
        )

    result = []
    for channel in matching_channels:
        try:
            # Extract number from channel name
            match = re.search(r'-(\d+)-', channel.name)
            if not match:
                logger.warning(f"Could not extract number from channel name: {channel.name}")
                continue # Skip channel if number pattern not found

            channel_number = match.group(1)
            # Create a regex pattern that matches 'team' followed anywhere by the number
            pattern = re.compile(r'team.*' + re.escape(channel_number), re.IGNORECASE)

            # Filter roles that match the regex pattern from channel overwrites
            valid_roles = [role for role in channel.overwrites.keys() if isinstance(role, discord.Role) and
                           pattern.search(role.name)]

            result.append({"channel": channel, "role": valid_roles if valid_roles else []})
        except Exception as e:
            logger.error(f"Error processing channel {channel.name} for GCs: {e}")

    return result

async def send_message_to_channel(channel, message):
    """Send a message to a specific channel."""
    try:
        await channel.send(message)
        # logger.info(f"Message sent to channel: {channel.name}") # Can be noisy
    except discord.Forbidden:
        logger.warning(f"Failed to send message to {channel.name}, permission denied.")
    except discord.HTTPException as e:
        logger.error(f"HTTP error sending to {channel.name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending to {channel.name}: {e}")


async def send_message(member, message):
    if member.bot: # Don't try to DM bots
        # logger.info(f"Skipping DM to bot: {member.name}")
        return
    try:
        await member.send(message)
        logger.info(f"DM sent to: {member.name}")
    except discord.Forbidden:
        logger.error(f"Could not send DM to {member.name}: Forbidden (DMs likely disabled).")
    except discord.HTTPException as e:
         logger.error(f"Could not send DM to {member.name}: HTTPException {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending DM to {member.name}: {e}")

# --- End Helper Functions ---


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        # Sync specific guild or globally if needed
        # synced = await bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID)) # Example for one guild
        synced = await bot.tree.sync() # Sync globally
        print(f"Synced: {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")


# Test ping command
@bot.tree.command(name='ping')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"{round(bot.latency * 1000)}ms {interaction.user.mention}!")


# send dm to each member with the specified roles with a message, doesnt accept user mentions, only role mentions
@bot.tree.command(name='senddmbyrole')
@app_commands.describe(message='The message to be sent to each role Member', rolesstring='Enter as many roles as you wish to DM')
@app_commands.checks.has_permissions(administrator=True) # Example permission check
async def senddmbyrole(interaction: discord.Interaction, message: str, rolesstring: str):
    """ Sends a DM to all members with the specified roles. """
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Command must be used within a server.", ephemeral=True)
        return

    role_ids = get_mentions_asid(rolesstring)
    if not role_ids:
        await interaction.response.send_message("No valid role mentions found in the input.", ephemeral=True)
        return

    roles = [guild.get_role(role_id) for role_id in role_ids]
    roles = [role for role in roles if role is not None] # Filter out None roles

    if not roles:
        await interaction.response.send_message("None of the mentioned roles were found in this server.", ephemeral=True)
        return

    members_to_dm = set()
    for role in roles:
        # Ensure members intent is working and cache is populated
        # Fetch members if necessary, though role.members should work if intents/cache are okay
        # await guild.chunk() # Might be needed if cache is incomplete, use cautiously
        for member in role.members:
            members_to_dm.add(member)

    if not members_to_dm:
        await interaction.response.send_message("No members found with the specified roles.", ephemeral=True)
        return

    await interaction.response.send_message(f"Sending DMs to {len(members_to_dm)} members... This may take a moment.", ephemeral=True)

    tasks = [send_message(member, message) for member in members_to_dm]
    # Gather tasks with error handling if needed, though send_message has some
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Count successes/failures (optional)
    success_count = sum(1 for r in results if r is None) # send_message returns None on success
    fail_count = len(results) - success_count

    await interaction.followup.send(f"Finished sending DMs. Success: {success_count}, Failed/Skipped: {fail_count}.", ephemeral=True)

@senddmbyrole.error
async def senddmbyrole_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
    else:
        logger.error(f"Error in senddmbyrole command: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
        else:
            await interaction.followup.send("An unexpected error occurred.", ephemeral=True)


# send dm to each member with the specified users with a message, doesnt accept role mentions, only user mentions
@bot.tree.command(name='senddm')
@app_commands.describe(message='The message to be sent to each member', usersstring='Enter as many users as you wish to DM')
@app_commands.checks.has_permissions(administrator=True) # Example permission check
async def senddm(interaction: discord.Interaction, message: str, usersstring: str):
    """ Sends a DM to all specified users. """
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Command must be used within a server.", ephemeral=True)
        return

    # --- FIX: Use the correct function for user mentions ---
    user_ids = get_user_mentions_asid(usersstring)
    # --- End FIX ---

    if not user_ids:
        await interaction.response.send_message("No valid user mentions found in the input.", ephemeral=True)
        return

    # Fetch members using IDs
    members_to_dm = []
    not_found_ids = []
    for user_id in user_ids:
        member = guild.get_member(user_id)
        if member:
            members_to_dm.append(member)
        else:
            # Try fetching if not in cache (requires members intent)
            try:
                member = await guild.fetch_member(user_id)
                if member:
                    members_to_dm.append(member)
                else:
                    not_found_ids.append(str(user_id))
            except discord.NotFound:
                not_found_ids.append(str(user_id))
            except discord.HTTPException as e:
                 logger.error(f"HTTP error fetching member {user_id}: {e}")
                 not_found_ids.append(f"{user_id} (fetch error)")


    if not members_to_dm:
        await interaction.response.send_message("None of the mentioned users could be found in this server.", ephemeral=True)
        return

    await interaction.response.send_message(f"Sending DMs to {len(members_to_dm)} members... This may take a moment.", ephemeral=True)

    if not_found_ids:
        await interaction.followup.send(f"Note: Could not find users with IDs: {', '.join(not_found_ids)}", ephemeral=True)

    tasks = [send_message(member, message) for member in members_to_dm]
    results = await asyncio.gather(*tasks, return_exceptions=True) # Removed unnecessary batching

    success_count = sum(1 for r in results if r is None)
    fail_count = len(results) - success_count

    await interaction.followup.send(f"Finished sending DMs. Success: {success_count}, Failed/Skipped: {fail_count}.", ephemeral=True)

@senddm.error
async def senddm_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
    else:
        logger.error(f"Error in senddm command: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
        else:
            await interaction.followup.send("An unexpected error occurred.", ephemeral=True)


@bot.tree.command(name='verifyroles', description='Verify each role against the channel name.')
@app_commands.checks.has_permissions(manage_channels=True, manage_roles=True) # Example permissions
async def verifyroles(interaction: discord.Interaction):
    """Search for channels that contain a specific string in their name."""
    guild = interaction.guild
    if guild:
        await interaction.response.defer(ephemeral=True) # Defer if get_GCs might take time
        results = get_GCs(guild)
        response = format_GCs_results(results)
        if not response:
            response = "No channels found matching '-group-chat' or no roles match the 'team + number' criteria."
        # Ensure response isn't too long for a single message
        if len(response) > 1950:
             response = response[:1950] + "\n... (output truncated)"
        await interaction.followup.send(response, ephemeral=True)
    else:
         await interaction.response.send_message("Command must be used within a server.", ephemeral=True)

@verifyroles.error
async def verifyroles_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need 'Manage Channels' and 'Manage Roles' permissions.", ephemeral=True)
    else:
        logger.error(f"Error in verifyroles command: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
        else:
            await interaction.followup.send("An unexpected error occurred.", ephemeral=True)


# --- Reminder Cancellation Implementation ---

# Dictionary to keep track of active reminder tasks {interaction_id: task}
# Note: This is in-memory only. Reminders are lost on bot restart.
active_reminder_tasks = {}

class CancelView(discord.ui.View):
    def __init__(self, task_to_cancel: asyncio.Task, interaction_id: int):
        # Timeout=None means the view persists until manually stopped or bot restarts
        super().__init__(timeout=None)
        self.task_to_cancel = task_to_cancel
        self.interaction_id = interaction_id
        self.cancel_button.custom_id = f"cancel_reminder_{interaction_id}" # Unique ID per reminder

    @discord.ui.button(label="Cancel Reminder", style=discord.ButtonStyle.danger) # custom_id set in __init__
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancels the associated reminder task."""
        if self.task_to_cancel and not self.task_to_cancel.done():
            self.task_to_cancel.cancel()
            logger.info(f"Reminder task {self.task_to_cancel.get_name()} cancelled by user {interaction.user} (ID: {interaction.user.id}).")
            await interaction.response.send_message("Reminder cancelled successfully!", ephemeral=True)
            # Optionally disable the button after cancellation
            button.disabled = True
            button.label = "Cancelled"
            await interaction.edit_original_response(view=self)
            # Remove from active tasks dict
            if self.interaction_id in active_reminder_tasks:
                del active_reminder_tasks[self.interaction_id]
        else:
            await interaction.response.send_message("This reminder has already finished or could not be cancelled.", ephemeral=True)
            button.disabled = True
            button.label = "Finished/Cancelled"
            await interaction.edit_original_response(view=self)

        # Stop the view from listening to further interactions for this button
        self.stop()

async def _run_reminder_task(delay: float, guild: discord.Guild, message: str, interaction: discord.Interaction):
    """The actual coroutine that waits and sends messages for a reminder."""
    task_name = f"reminder_{interaction.id}"
    try:
        # Assign a name for easier identification in logs/debugging
        asyncio.current_task().set_name(task_name)
        logger.info(f"Task {task_name}: Starting reminder, sleeping for {delay:.2f} seconds.")
        # Wait for the specified delay. If cancelled during sleep, raises CancelledError.
        await asyncio.sleep(delay)

        # If sleep completes without cancellation, proceed to send messages
        logger.info(f"Task {task_name}: Waking up, fetching channels and sending messages.")
        results = get_GCs(guild)
        if not results:
             logger.warning(f"Task {task_name}: No group chat channels found when reminder triggered.")
             await interaction.followup.send("Reminder triggered, but no matching group chat channels were found.", ephemeral=True)
             return

        tasks = []
        for item in results:
            channel = item['channel']
            roles = item['role']
            if roles: # Ensure there's at least one role to mention
                # Mention the first role found associated with the channel
                mention = f'<@&{roles[0].id}>'
                tasks.append(send_message_to_channel(channel, f"{message} {mention}"))
            else:
                # Decide what to do if no role found: send without mention or skip?
                logger.warning(f"Task {task_name}: No matching role found for channel {channel.name}, sending reminder without mention.")
                tasks.append(send_message_to_channel(channel, message)) # Send without mention

        if tasks:
            await asyncio.gather(*tasks) # Send all messages concurrently
            logger.info(f"Task {task_name}: Sent reminder messages to {len(tasks)} channels.")
            await interaction.followup.send(f"Reminder message sent to {len(tasks)} channels.", ephemeral=False) # Send confirmation publicly
        else:
             logger.info(f"Task {task_name}: No messages were sent (all channels lacked roles?).")
             await interaction.followup.send("Reminder triggered, but no messages could be sent (check channel/role setup?).", ephemeral=True)

    except asyncio.CancelledError:
        # This block executes if task.cancel() was called (e.g., by the button)
        logger.info(f"Task {task_name}: Successfully cancelled.")
        # Optionally send a confirmation that it was indeed cancelled via followup
        try:
            await interaction.followup.send("Reminder was cancelled.", ephemeral=True)
        except discord.NotFound:
             logger.warning(f"Task {task_name}: Could not send cancellation followup (original interaction deleted?).")
        except Exception as e:
             logger.error(f"Task {task_name}: Error sending cancellation followup: {e}")

    except Exception as e:
        # Catch any other unexpected errors during the task execution
        logger.error(f"Task {task_name}: An error occurred: {e}", exc_info=True)
        try:
            await interaction.followup.send(f"An error occurred while executing the reminder: {e}", ephemeral=True)
        except Exception as followup_e:
            logger.error(f"Task {task_name}: Failed to send error followup message: {followup_e}")

    finally:
        # Clean up: Remove the task from the tracking dictionary regardless of outcome
        if interaction.id in active_reminder_tasks:
            del active_reminder_tasks[interaction.id]
            logger.info(f"Task {task_name}: Removed from active tasks.")


@bot.tree.command(name='set_reminder', description='Set a reminder to send messages to channels.')
@app_commands.describe(
    reminder_time="When to send (e.g., 'in 2 hours', 'tomorrow 10am EST', '2025-12-25 09:00 PST')",
    reminder_message="The message content to send (role mention will be added)."
)
@app_commands.checks.has_permissions(administrator=True) # Example permission
async def set_reminder(interaction: discord.Interaction, reminder_time: str, reminder_message: str):
    """Sets a reminder to message all '-group-chat' channels at a specific time."""
    if not interaction.guild:
         await interaction.response.send_message("Command must be used within a server.", ephemeral=True)
         return

    try:
        # Attempt to parse the user-provided time string
        # Use dateutil.parser which is quite flexible
        now_aware = datetime.datetime.now(datetime.timezone.utc) # Use timezone-aware current time (UTC)

        try:
            # Let dateutil try to figure out timezone info if provided
            reminder_dt_maybe_aware = dateutil.parser.parse(reminder_time)
        except ValueError:
            await interaction.response.send_message(
                "Invalid time format. Please use a format like 'YYYY-MM-DD HH:MM:SS TZ', 'in 5 minutes', 'tomorrow 3pm EST', etc.",
                ephemeral=True
            )
            return
        except OverflowError:
             await interaction.response.send_message("The specified date is too far in the future.", ephemeral=True)
             return

        # If parsed time is naive, assume user meant bot's local time (or UTC as fallback)
        # For simplicity, we'll assume UTC if no timezone info is parsed.
        # A more robust solution might involve server settings or user profiles for timezones.
        if reminder_dt_maybe_aware.tzinfo is None or reminder_dt_maybe_aware.tzinfo.utcoffset(reminder_dt_maybe_aware) is None:
            # Make it aware, assuming UTC. You might want to adjust this based on your bot's expected userbase.
            reminder_dt_aware = reminder_dt_maybe_aware.replace(tzinfo=datetime.timezone.utc)
            logger.warning(f"Reminder time '{reminder_time}' was timezone-naive, assuming UTC. Result: {reminder_dt_aware}")
        else:
            # If already aware, convert to UTC for consistent internal handling
            reminder_dt_aware = reminder_dt_maybe_aware.astimezone(datetime.timezone.utc)

        # Calculate delay in seconds
        delay = (reminder_dt_aware - now_aware).total_seconds()

        if delay <= 0:
            await interaction.response.send_message("The specified time is in the past.", ephemeral=True)
            return

        # Check for excessively long delays if desired (e.g., > 1 year)
        max_delay = 365 * 24 * 60 * 60 # Example: 1 year
        if delay > max_delay:
             await interaction.response.send_message("Reminders cannot be set more than a year in the future.", ephemeral=True)
             return

        # --- Task Creation and View Setup ---
        # Create the coroutine object for the reminder task
        reminder_coro = _run_reminder_task(delay, interaction.guild, reminder_message, interaction)

        # Create the actual asyncio task
        reminder_task = asyncio.create_task(reminder_coro)

        # Store the task reference using interaction ID as key
        active_reminder_tasks[interaction.id] = reminder_task
        logger.info(f"Created and stored reminder task {reminder_task.get_name()} for interaction {interaction.id}.")

        # Create the view, passing the task to it for cancellation
        view = CancelView(task_to_cancel=reminder_task, interaction_id=interaction.id)
        # --- End Task Creation ---

        # Respond to the user
        hours, remainder = divmod(delay, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_string = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        # Format reminder time clearly using UTC
        formatted_time = reminder_dt_aware.strftime('%Y-%m-%d %H:%M:%S %Z') # e.g., 2025-12-25 14:00 UTC

        await interaction.response.send_message(
            f"Reminder set for **{formatted_time}** (in {time_string}). Message: '{reminder_message[:100]}{'...' if len(reminder_message)>100 else ''}'",
            view=view # Attach the view with the cancel button
        )

    except Exception as e:
        logger.error(f"Error in set_reminder command: {e}", exc_info=True)
        # Try to send an error message back to the user
        error_message = f"An unexpected error occurred while setting the reminder: {e}"
        if not interaction.response.is_done():
            await interaction.response.send_message(error_message, ephemeral=True)
        else:
            # If we already responded (e.g., defer), use followup
            await interaction.followup.send(error_message, ephemeral=True)

@set_reminder.error
async def set_reminder_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
    else:
        # Log other errors, potentially handled in the main try/except already
        logger.error(f"Unhandled error in set_reminder check/dispatch: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("An error occurred processing this command.", ephemeral=True)


# --- Bot Run ---
if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Error: DISCORD_TOKEN not found in environment variables/.env file.")
    else:
        try:
            bot.run(token)
        except discord.LoginFailure:
            print("Error: Invalid Discord Token. Please check your .env file.")
        except Exception as e:
            print(f"Error running bot: {e}")

