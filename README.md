# Serverify

This script has only been tested in Modpacks installed with CurseForge.

This script inspects any modpack folder the user points at, then identifies the client-side mods and makes a copy of the (instance) folder containing a server-side-only mods folder. It is always under the format (instance name).serverside, the path to it is C:\...\curseforge\minecraft\Instances. It's important to know that by creating a copy of the folder, the server-side instance will take up as much space (if not a little less) as the original one. If you are running very low on storage space or the instance's folder is exceedingly large, consider that the process, if it finishes, will take longer.

The part of this code used for identifying client-side mods was written by laurorual, and therefore needs the same packages (requests and tqdm, plus tomli if you use a version of Python under 3.11).
The original script is in Portuguese, however this (modified) version has been translated into English. You can find the original project here:
https://github.com/laurorual/Mod-Checker.git

Transparency note: AI was used while writing some parts of this script.

# How to use

On a python terminal, run the script as:

    python makecopy.py --dir C:\...\curseforge\minecraft\Instances\(wanted instance)\mods