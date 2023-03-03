from dotenv import load_dotenv
import pymongo
import update_check as updater
import random
from MeowerBot import Bot
import requests
import os
import time

# Version tracker
version = "1.0.0"

# Load environment keys
if not load_dotenv():
    print("Failed to load .env keys, exiting.")
    exit()

# Create instance of bot
octavia = Bot()

# Keep track of processing responses
newResponses = dict()

# Prepare DB connection
print(f"Connecting to database...")
dbclient = pymongo.MongoClient(os.getenv("SERVER_DB", "mongodb://localhost:27017"))
octaviadb = None

# Check DB connection status
try:
    dbclient.server_info()
    print("Connected to database!")
    octaviadb = dbclient.octavia
except pymongo.errors.ServerSelectionTimeoutError as err:
    print(f"Failed to connect to database: \"{err}\"!")
    exit()


# Restart script
def restart():
    print("Shutting down websocket")
    octavia.wss.stop()

    script = os.getenv("RESET_SCRIPT")
    print(f"Running reset script: {script}")
    os.system(script)

    print(f"Takko {version} going away now...")
    exit()


# Shutdown script
def shutdown():
    print("Shutting down websocket")
    octavia.wss.stop()

    print(f"Takko {version} going away now...")
    exit()


# Get a startup message from the DB
def getRandomStartupMessage():
    # Get all possible messages
    messages = list(octaviadb.introductions.find())
    intro = random.choice(messages)["msg"]
    print(f"Picking random introductions from a set of {len(messages)} intros... I choose \"{intro}\".")
    return intro


# Retrieve a response
def getResponse(question):
    response = octaviadb.memory.find_one({"msg": question})
    if response:
        print(f"Lookup for question: \"{question}\", returned: {response['resp']}")
        return True, response["resp"]
    else:
        print(f"Lookup for question: \"{question}\", found nothing.")
        return False, None


# Create a response
def createResponse(question, response, creator):
    result = octaviadb.memory.insert_one(
        {
            "msg": question,
            "resp": response,
            "creator": creator,
            "timestamp": time.time()
        }
    )
    print(f"Creating response \"{response}\" for question: \"{question}\" results with new ID: {result.inserted_id}")


# Commands
@octavia.command(args=0, aname="help")
def help(ctx):
    ctx.send_msg("Just start talking to me, and I'll reply to the best of my ability! \nIf I don't know how to reply to a question, you can use \n@Takko add (reply) to help me, or use @Takko cancel to stop. \nYou can learn about me with @Takko about. \nThere are a few commands I've inherited from MeowyMod, but only JoshAtticus can use them.")


# Display info
@octavia.command(args=0, aname="about")
def about(ctx):
    ctx.send_msg(
        f"I'm Takko v{version}! \n\nI was created by @JoshAtticus. I'm based upon MeowyMod. I was built using ShowierData9978's MeowerBot.py library! \n\nYou can find my source code here: https://github.com/JoshAtticus/Takko")


# Update check
@octavia.command(args=0, aname="update")
def updateCheck(ctx):
    if ctx.user.username == "JoshAtticus":
        # Check for updates, but better(ish)
        versionHistory = requests.get("https://raw.githubusercontent.com/JoshAtticus/Takko/main/versionInfo.json").json()
        if version not in versionHistory["latest"] or version in versionHistory["old"]:
            ctx.send_msg(f"Looks like I'm out-of-date! Latest version(s) are {versionHistory['latest']} while I'm on {version}. Downloading updates...")
            time.sleep(1)
            updater.update(f"{os.getcwd()}/main.py", "https://raw.githubusercontent.com/JoshAtticus/Takko/main/src/main.py")
            ctx.send_msg("Rebooting to apply updates...")
            time.sleep(1)
            restart()
        else:
            ctx.send_msg(f"Looks like I'm up-to-date! Running v{version} right now.")
    else:
        ctx.send_msg(f"You're not JoshAtticus. Go away.")


# Reboot request
@octavia.command(args=0, aname="reboot")
def rebootScript(ctx):
    if ctx.user.username == "JoshAtticus":
        ctx.send_msg("Gimme just a moment...")
        restart()
    else:
        ctx.send_msg(f"You're not JoshAtticus. Go away.")


# Shutdown request
@octavia.command(args=0, aname="shutdown")
def shutdownScript(ctx):
    if ctx.user.username == "JoshAtticus":
        ctx.send_msg("Back to bed, I suppose...")
        shutdown()
    else:
        ctx.send_msg(f"You're not JoshAtticus. Go away.")


# Finish adding new response
@octavia.command(args=0, aname="add")
def addNewResponse(ctx, *args):
    if ctx.user.username in newResponses:
        # Remove command and prefix
        msg = ctx.message._raw["p"].replace("add ", "", 1)
        msg = msg.replace((octavia.prefix + " "), "", 1)
        
        # Create response in the DB
        createResponse(newResponses[ctx.user.username], msg, ctx.user.username)
        
        # Return
        ctx.send_msg(f"@{ctx.user.username} Thanks! I'll respond with \"{msg}\" in the future~")
        del newResponses[ctx.user.username]
    else:
        ctx.send_msg(f"@{ctx.user.username} I didn't ask for an answer from you yet. Just continue chatting with me for now. Using add without me knowing what to add to my memory can get confusing really fast.")


# Abort adding a new response
@octavia.command(args=0, aname="cancel")
def abortNewResponse(ctx):
    if ctx.user.username in newResponses:
        ctx.send_msg(f"@{ctx.user.username} Sure, let's continue chatting~")
        del newResponses[ctx.user.username]
    else:
        ctx.send_msg(f"@{ctx.user.username} I didn't ask for an answer from you yet. Just continue chatting with me for now. Using cancel without me knowing what to purge from my memory can get confusing really fast.")


# Full messages
def fullQuestionEventManager(message, bot):
    origin = message["u"]
    question = message["p"].split(bot.prefix, 1)[1]
    question = question[1:]
    print(f"Got a question from {origin}: {question}")
    valid, response = getResponse(question)
    if valid:
        bot.send_msg(f"@{origin} {response}")
    else:
        if origin in newResponses:
            return
        newResponses[origin] = question
        bot.send_msg(f"@{origin} I don't know how to respond to that question yet, but you can provide me with an answer! Just use @Takko add (response), or just tell me @Takko cancel.")


# Listener management
def listenerEventManager(post, bot):
    # Validate keys
    for key in ["cmd", "val", "listener"]:
        if key not in post:
            return
    
    # Handle startup message
    if post["cmd"] == "statuscode" and post["listener"] == "__meowerbot__login" and post["val"] == "I:100 | OK":
        bot.send_msg(f"{getRandomStartupMessage()}")


# Register event listener for questions and startup message
octavia.callback(listenerEventManager, cbid="__raw__")
octavia.callback(fullQuestionEventManager, cbid="raw_message")


# Display startup message in console
print(f"Octavia {version} starting up now...")


# Run bot
try:
    octavia.run(
        username=os.getenv("BOT_USERNAME"),
        password=os.getenv("BOT_PASSWORD"),
        server=os.getenv("SERVER_CL")
    )
except KeyboardInterrupt:
    print("Detecting interrupt, going away now...")
    shutdown()
