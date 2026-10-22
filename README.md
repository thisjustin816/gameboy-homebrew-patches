# Game Boy homebrew patches

Patches for Game Boy and Game Boy Color homebrew games: save systems the games
shipped without, and fixes for bugs that never got patched.

> The patches and their tools were developed with Claude. Link Sustain was
> developed with Codex, and its screens were redesigned with Claude. Platform
> Detect was developed with Codex and extended with Claude. Each README says how it was tested.

Each patch comes as an IPS file for a specific release of a game, plus the
source it's built from. **Commercial game ROMs are not included.** Bring your
own copy of the game, and check its md5 against the patch's README first. Each
patch is made for one exact release, and the build script refuses any other.
Original standalone diagnostic ROMs are included with their matching source.
The Disney Afternoon Collection is another exception: it combines four ROMs
into one, so it comes as a build script instead of an IPS file.

| Game | Folder | What the patch does |
|---|---|---|
| Hermano / Hermano (ModRetro) | [`hermano/`](hermano/) | Adds a battery save. The game saves during play, and **B** on the title screen resumes. Covers the original release and the ModRetro Chromatic release. |
| Roguecraft GB | [`roguecraft/`](roguecraft/) | Saves a run to resume later: arriving on each floor saves it, and START GAME offers **RESUME GAME**. Also fixes the chest count on the end screen, chests that could be opened twice, and enemies that go invisible after the mini-map closes. The title screen reads `v1.000b`, and the RESUME GAME menu clears the title's menu away while it's up. |
| Bubble Bobble | [`bubblebobble/`](bubblebobble/) | Adds a battery save: the last round started is remembered, and the PASSWORD screen opens with its password already filled in. |
| Classic Bubble Bobble | [`classicbubblebobble/`](classicbubblebobble/) | Makes Bub jump, fall and shoot like the Master System version: a faster, higher-arcing jump with more control in the air, quicker falls off ledges, and a shot that snaps out twice as fast over the same distance. Also adds a battery save: the last round started is remembered, and the PASSWORD screen opens with its password already filled in. |
| Bubble Bobble Part 2 | [`bubblebobble2/`](bubblebobble2/) | Stops the screen from tearing while the camera scrolls. The game wrote the scroll registers partway down the picture; the patch makes those writes wait for VBlank. Also adds a battery save: the last stage started is remembered, and the PASSWORD screen opens with its password already filled in. |
| Legion of Evil | [`legionofevil/`](legionofevil/) | Adds a battery save for upgrades and money, a title menu (continue, new run, erase save), and a pause menu that can save a run partway through and continue it later. On a Game Boy Color or ModRetro Chromatic it runs in color at double speed with 16 selectable themes, which removes most slowdown, and keeps the player sprite from disappearing in crowds. Hits flash the player, and the rumble patch runs a rumble motor on hits and when a boss comes in. Also fixes a strip at the top of the screen that shifted when the camera scrolled. |
| Disney Afternoon Collection | [`disney-afternoon/`](disney-afternoon/) | Puts DuckTales, DuckTales 2, TaleSpin and Darkwing Duck on one cart, with a splash and a game menu drawn from the PC Disney Afternoon Collection's art. Each game runs exactly as on its own cart. |

## Diagnostic tools

[Link Sustain](diagnostics/link-cable-test/) is a standalone Game Boy Color
link-cable test. It continuously exchanges packets in both directions, checks
CRCs and sequence numbers, and keeps the first failure after sync recovers.
Its source and tests are included; building it requires GBDK-2020.

[Platform Detect](diagnostics/platform-detect/) is a standalone Game Boy / Game
Boy Color runtime diagnostic. It reports the hardware class and, in CGB mode,
checks twelve registers for behavior a Game Boy Color never shows, then says
whether the host is likely an emulator and names it when the pattern is known.
Its source and verified ROM are included; building it requires GBDK-2020 4.5.0.

## Releases

Each release holds one game's `.ips` files, a `checksums.txt` with their
sha256, and notes with what the patch does and the supported stock md5s, both
taken from the game's README, how to apply it, and a link to that README. For a
game with more than one patch, the notes also say which patch is which, from
the table of patches at the top of its README, and the workflow stops if that
table leaves out a patch, names a file that is not in the folder, or has a row
without the md5 after patching. A release never includes a ROM.

To cut one, open the **Actions** tab, pick **Release**, click **Run workflow**
on `main`, then pick the game and type its version. A patch for a classic game
has a version of its own, two numbers such as `1.1`, separate from the game's.
A patch for a modern game carries on the game's own version string, such as
`1.000b`, in whatever form the game uses, so the workflow only checks that it
holds characters that are safe in a tag name: letters, digits and `. _ + -`.
The workflow keeps the list of which games are which, and refuses a version
that does not fit the game's kind. Where the game's README names a
version, in its Versions list, the ROM name in its build command or the title
screen's mark, use the newest, without its `v`. The workflow creates the
release and its tag, `<game>-v<version>`, for example `legionofevil-v1.2`, on
the commit it ran from, and stops if that tag already exists. A classic game's
release is named after its patch, from the README's title with its colon as a
dash, such as `Bubble Bobble - last-round save`, and only its tag carries the
version. A modern game's release is named with the game and its version, such
as `Legion of Evil v1.2`.

## Applying a patch

Use any IPS patcher, for example
[Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) in a browser, or
Floating IPS. Pick your unmodified ROM and the patch's `.ips` file, from the
game's release or its folder, then save the result under a new name.

To keep an existing save, rename your `.sav` to match the patched ROM's
filename. Most emulators and flash carts look for a save with the same name as
the ROM.

## Building a patch

Each folder has the assembly source, the patch script and a test script. Only
Python 3 is needed to build:

```
cd roguecraft
python3 patch.py Roguecraft_GB.gbc -o Roguecraft_GB-save.gbc --ips Roguecraft-save.ips
```

The test scripts (`verify.py STOCK PATCHED`) run the stock and patched ROMs in
[PyBoy](https://github.com/Baekalfen/PyBoy) (`pip install pyboy pillow`) and
check each change against the stock game. Bubble Bobble crashes in PyBoy once a
round starts, so its script plays the game in Gambatte through
[stable-retro](https://github.com/Farama-Foundation/stable-retro) as well.
Each folder's README explains what the patch changes and how it was tested.

## Shared scripts

The code every game's scripts use lives in [`common/`](common/): `asm.py`, the
small LR35902 assembler; `ips.py`, which writes and applies IPS patches; and
`checksum.py`, the header and global checksums. Each script that imports from
`common/` adds it to its import path, so the commands above still run from
inside a game's folder. A change to `common/` reaches every patch, so after one,
run `python3 common/test_ips.py`, then rebuild each patch and check that its
IPS comes out the same as the committed one.
