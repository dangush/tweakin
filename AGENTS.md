# Working on tweakin

Keep the installed skill self-contained under `skills/tweakin`. Resolve bundled resources from the script's location and accept user-specific inputs through explicit arguments.

Keep Markdown paragraphs and list items on one physical line.

Run `python3 -m unittest discover -s tests -v` after changing the build tool. Compile the native source on macOS after changing the patch. Run `python3 scripts/check_public.py` after staging a change. Update `public-files.json` deliberately when adding a distributable file.

Use synthetic test inputs in the repository. Keep app binaries, personalized licenses, signing files, accounts, device identifiers, and generated reports outside the checkout. CI must not acquire an app or authenticate to Apple.

Distinguish static inspection, source compilation, signature verification, and phone acceptance. Preserve version-specific evidence and limitations when updating a recipe. A hook that installs successfully still needs behavioral testing.
