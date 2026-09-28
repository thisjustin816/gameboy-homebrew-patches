# Game Boy homebrew patches

Patches for Game Boy and Game Boy Color homebrew games: save systems the games
shipped without, and fixes for bugs that never got patched.

> **Claude-assisted.** The patches, tools and documentation in this repo were
> made with the help of Claude, Anthropic's AI assistant. Each patch's README
> says how it was tested.

Each patch comes as an IPS file for a specific release of a game, plus the
source it's built from. **There are no ROMs here.** Bring your own copy of the
game, and check its md5 against the patch's README first. Each patch is made
for one exact release, and the build script refuses any other.

| Game | Folder | What the patch does |
|---|---|---|
| Hermano / Hermano World | [`hermano/`](hermano/) | Adds a battery save. The game autosaves as you play, and **B** on the title screen resumes. Covers the original release and the ModRetro Chromatic release. |
| Roguecraft GB | [`roguecraft/`](roguecraft/) | Lets you resume a run: arriving on each floor saves it, and START GAME offers **RESUME GAME**. Also fixes the chest count on the end screen, chests that could be opened twice, and enemies that go invisible after you look at the mini-map. The title screen reads `v1.000+`. |

## Applying a patch

Use any IPS patcher, for example
[Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) in a browser, or
Floating IPS. Pick your unmodified ROM and the patch's `.ips` file, then save
the result under a new name.

To keep an existing save, rename your `.sav` to match the patched ROM's
filename. Most emulators and flash carts look for a save with the same name as
the ROM.

## Building a patch yourself

Each folder has the assembly source, a small assembler, the patch script and a
test script. Only Python 3 is needed to build:

```
cd roguecraft
python3 patch.py Roguecraft_GB.gbc -o Roguecraft_GB-save.gbc --ips Roguecraft-save.ips
```

The test scripts (`verify.py STOCK PATCHED`) run the stock and patched ROMs in
[PyBoy](https://github.com/Baekalfen/PyBoy) (`pip install pyboy pillow`) and
check each change against the stock game. Each folder's README explains what the
patch changes and how it was tested.
