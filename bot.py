import discord
from discord.ext import commands
import random
import json
import string
from collections import Counter

# Remove the default help command so we can use our custom one
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, activity=discord.Game(name="Codebusters"))
bot.remove_command("help")  # Removes the default built-in help command

def load_quotes():
    try:
        with open('quotes.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_quotes(quotes):
    with open('quotes.json', 'w') as f:
        json.dump(quotes, f)

# Store active puzzles for different users
active_puzzles = {}

class Puzzle:
    def __init__(self, plaintext):
        self.plaintext = plaintext.lower()
        self.cipher_mapping = {}
        self.user_guesses = {}
        self.generate_cipher()
    
    def generate_cipher(self):
        alphabet = list(string.ascii_lowercase)
        shuffled = list(string.ascii_uppercase)
        random.shuffle(shuffled)
        self.cipher_mapping = dict(zip(alphabet, shuffled))
    
    def get_ciphertext(self):
        return ''.join(self.cipher_mapping.get(c, c) for c in self.plaintext)
    
    def get_current_guess(self):
        """
        Return a string showing underscores for unguessed letters,
        and the correct lowercase letter for any correctly guessed letters.
        Non-alpha chars remain as-is.
        """
        ciphertext = self.get_ciphertext()
        result = []
        for char in ciphertext:
            if char.isalpha() and char in self.user_guesses:
                result.append(self.user_guesses[char])
            elif char.isalpha():
                result.append('_')
            else:
                result.append(char)
        return ''.join(result)
    
    def make_guess(self, cipher_char, plain_char):
        """
        Checks if cipher_char (uppercase) actually maps to plain_char (lowercase).
        If correct, store in user_guesses and return True, otherwise False.
        """
        if not (cipher_char.isupper() and plain_char.islower()):
            return False

        # Identify correct plaintext letter for this cipher_char from cipher_mapping
        for real_plain_char, mapped_cipher_char in self.cipher_mapping.items():
            if mapped_cipher_char == cipher_char:
                if real_plain_char == plain_char:
                    self.user_guesses[cipher_char] = plain_char
                    return True
                else:
                    return False
        return False
    
    def undo_guess(self, cipher_char):
        """
        Removes a single-letter guess if it exists in user_guesses.
        """
        if cipher_char in self.user_guesses:
            del self.user_guesses[cipher_char]
            return True
        return False
    
    def clear_guesses(self):
        """
        Clears all guesses.
        """
        self.user_guesses.clear()
    
    def is_solved(self):
        """
        Returns True if the user's current guess matches the original plaintext exactly.
        """
        return (self.get_current_guess() == self.plaintext)
    
    def give_hint(self):
        """
        Reveals ONE random letter that hasn't been guessed yet.
        Returns (cipher_char, plain_char) if a letter was revealed, or None if no hint is possible.
        """
        ciphertext = self.get_ciphertext()
        
        # Build a list of cipher characters that are not yet guessed
        unguessed = []
        for cipher_char in ciphertext:
            if cipher_char.isalpha() and cipher_char not in self.user_guesses:
                unguessed.append(cipher_char)
        
        if not unguessed:
            return None  # No letters to reveal
        
        # Randomly choose one unguessed cipher character
        chosen_cipher = random.choice(unguessed)
        
        # Figure out the correct plaintext letter for that cipher character
        for real_plain_char, mapped_cipher_char in self.cipher_mapping.items():
            if mapped_cipher_char == chosen_cipher:
                # Reveal that letter
                self.user_guesses[chosen_cipher] = real_plain_char
                return (chosen_cipher, real_plain_char)
        
        return None

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command(name='newpuzzle')
async def new_puzzle(ctx):
    quotes = load_quotes()
    if not quotes:
        await ctx.send("No quotes available in the database!")
        return
    
    quote = random.choice(quotes)
    puzzle = Puzzle(quote)
    active_puzzles[ctx.author.id] = puzzle
    
    await display_puzzle(ctx)

@bot.command(name='guess')
async def guess(ctx, cipher_char: str, plain_char: str):
    puzzle = active_puzzles.get(ctx.author.id)
    if not puzzle:
        await ctx.send("No active puzzle! Use !newpuzzle to start one.")
        return
    
    success = puzzle.make_guess(cipher_char.upper(), plain_char.lower())
    if success:
        if puzzle.is_solved():
            await ctx.send("Congratulations! You've correctly solved the entire puzzle!")
            del active_puzzles[ctx.author.id]
        else:
            await display_puzzle(ctx)
    else:
        await ctx.send("Incorrect guess or invalid format. (cipher=UPPER, plain=lower)")

@bot.command(name='undo')
async def undo(ctx, cipher_char: str):
    puzzle = active_puzzles.get(ctx.author.id)
    if not puzzle:
        await ctx.send("No active puzzle! Use !newpuzzle to start one.")
        return
    
    if puzzle.undo_guess(cipher_char.upper()):
        await display_puzzle(ctx)
    else:
        await ctx.send("No guess found for that character.")

@bot.command(name='clear')
async def clear(ctx):
    puzzle = active_puzzles.get(ctx.author.id)
    if not puzzle:
        await ctx.send("No active puzzle! Use !newpuzzle to start one.")
        return
    
    puzzle.clear_guesses()
    await display_puzzle(ctx)

@bot.command(name='solve')
async def solve_puzzle(ctx, *, guess_text: str):
    puzzle = active_puzzles.get(ctx.author.id)
    if not puzzle:
        await ctx.send("No active puzzle! Use !newpuzzle to start one.")
        return
    
    # We'll remove punctuation/spaces to do a simpler comparison.
    # Or you can do a direct string compare if you want to match exactly (but it's more error-prone).
    def normalize(text):
        return ''.join(ch for ch in text.lower() if ch.isalnum())
    
    guess_norm = normalize(guess_text)
    plaintext_norm = normalize(puzzle.plaintext)
    
    if guess_norm == plaintext_norm:
        await ctx.send("Congratulations! You've correctly solved the entire puzzle!")
        del active_puzzles[ctx.author.id]
    else:
        await ctx.send("Sorry, that guess doesn't match the actual solution.")

@bot.command(name='addquote')
async def add_quote(ctx, *, quote: str):
    quotes = load_quotes()
    quotes.append(quote)
    save_quotes(quotes)
    await ctx.send("Quote added successfully!")

# ------------------------------ NEW: !hint and !answer ------------------------------ #
@bot.command(name='hint')
async def give_hint_command(ctx):
    """
    Reveals one random unguessed letter in the ciphertext.
    If no letters remain unguessed, or if there's no active puzzle, it notifies the user.
    """
    puzzle = active_puzzles.get(ctx.author.id)
    if not puzzle:
        await ctx.send("No active puzzle! Use !newpuzzle to start one.")
        return
    
    hint_result = puzzle.give_hint()
    if not hint_result:
        # That means no letters left to reveal or puzzle is complete
        if puzzle.is_solved():
            await ctx.send("Puzzle is already solved!")
        else:
            await ctx.send("All letters have been revealed or there's nothing to hint.")
        return
    else:
        cipher_char, plain_char = hint_result
        await ctx.send(f"Here's a hint: **{cipher_char}** maps to **{plain_char}**.")
    
    if puzzle.is_solved():
        await ctx.send("Congratulations! You've correctly solved the entire puzzle!")
        del active_puzzles[ctx.author.id]
    else:
        await display_puzzle(ctx)

@bot.command(name='answer')
async def show_answer(ctx):
    """
    Directly reveals the puzzle's plaintext and ends the puzzle (like 'giving up').
    """
    puzzle = active_puzzles.get(ctx.author.id)
    if not puzzle:
        await ctx.send("No active puzzle! Use !newpuzzle to start one.")
        return
    
    await ctx.send(f"The full answer was:\n\n**{puzzle.plaintext}**")
    # Remove the puzzle from active puzzles so user can't keep guessing
    del active_puzzles[ctx.author.id]
# ------------------------------------------------------------------------------------ #

@bot.command(name='help')
async def custom_help(ctx):
    """
    Custom help command that lists all bot commands and their usage.
    """
    embed = discord.Embed(title="Codebusters Bot Commands", color=0x00ff00)
    
    embed.add_field(
        name="!newpuzzle",
        value="Starts a new puzzle from the existing quote database.",
        inline=False
    )
    embed.add_field(
        name="!guess <CIPHER_CHAR> <PLAIN_CHAR>",
        value="Guess that the UPPERCASE cipher letter maps to the lowercase plain letter.\nExample: `!guess Q a`.",
        inline=False
    )
    embed.add_field(
        name="!undo <CIPHER_CHAR>",
        value="Removes your guess for the specified uppercase cipher letter.\nExample: `!undo Q`.",
        inline=False
    )
    embed.add_field(
        name="!clear",
        value="Clears **all** of your current letter guesses for the puzzle.",
        inline=False
    )
    embed.add_field(
        name="!solve <FULL_PLAINTEXT>",
        value="Attempts to solve the entire puzzle at once by providing a guess for the full phrase.\nExample: `!solve four score and seven years ago`",
        inline=False
    )
    embed.add_field(
        name="!hint",
        value="Reveals a single random letter from the unguessed ciphertext.",
        inline=False
    )
    embed.add_field(
        name="!answer",
        value="Reveals the entire plaintext and ends the current puzzle (like giving up).",
        inline=False
    )
    embed.add_field(
        name="!addquote <QUOTE>",
        value="Adds a new quote to the quote database. \nExample: `!addquote Life is 10% what happens to you and 90% how you react to it.`",
        inline=False
    )
    embed.add_field(
        name="!help",
        value="Displays this help message.",
        inline=False
    )

    await ctx.send(embed=embed)

async def display_puzzle(ctx):
    """
    Builds and sends an embed showing the puzzle's ciphertext, current guess, and letter frequency.
    """
    puzzle = active_puzzles[ctx.author.id]
    ciphertext = puzzle.get_ciphertext()
    
    # Build a frequency table
    freq_counter = Counter(ch for ch in ciphertext if ch.isalpha())
    freq_str = '\n'.join(f"{letter}: {freq_counter[letter]}" 
                         for letter in sorted(freq_counter))

    embed = discord.Embed(title="Codebusters Puzzle", color=0x00ff00)
    embed.add_field(name="Cipher Text", value=f"```{ciphertext}```", inline=False)
    embed.add_field(name="Your Guess", value=f"```{puzzle.get_current_guess()}```", inline=False)
    embed.add_field(name="Ciphertext Frequency", value=f"```{freq_str}```", inline=False)
    
    await ctx.send(embed=embed)

bot.run('MTMzMTM2OTU2MDcxNjIxODQyOA.GoaUmg.KBEIFATRQvETrShwhpARfre9FuGDrQtD-EbOtw')