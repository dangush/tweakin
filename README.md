# tweakin

An agent skill for developing native iOS app tweaks, with source and local build tools for an Instagram Focus recipe.

Ask your coding agent to change a specific behavior in an app you own. The skill guides binary inspection, hook development, signing, and phone testing. Its first recipe allows individual Reels while blocking the scrolling feed, removes the Reels tab, preserves search, limits Home, and removes Home and Story ads.

## Install the skill

Clone the repository, then copy the complete skill directory into Codex's skills directory. Keep the accompanying source, references, and licenses together.

```sh
git clone https://github.com/dangush/tweakin.git
mkdir -p "$HOME/.codex/skills"
cp -R tweakin/skills/tweakin "$HOME/.codex/skills/tweakin"
```

If that destination already exists, review and update it instead of copying another directory inside it. For another agent that supports `SKILL.md`, install the same directory using that agent's skill convention.

Example requests:

> Use $tweakin to build Instagram Focus from my decrypted Instagram 418.2.0 IPA with my own signing profile.

> Use $tweakin to investigate whether we can disable the short-video feed in another iOS app while preserving shared videos.

You can also run the [Instagram recipe](skills/tweakin/references/instagram.md) without an agent.

## What you supply

The Instagram build needs a Mac with Xcode and Python 3.10 or newer, a compatible decrypted IPA that you acquired yourself, and your own signing certificate and provisioning profile. You complete Apple authentication and phone trust prompts locally, then sign into Instagram on your phone. [Acquisition instructions](skills/tweakin/references/acquisition.md) describe the separate App Store and decryption steps.

This repository contains tweak source and tooling. Keep downloaded apps, generated IPAs, account sessions, signing material, and enrollment models outside the repository.

## Supported scope

The native Instagram tweak was accepted on Instagram 418.2.0 with iOS 18.6.2. Its Home limit is 30 distinct posts per feed data-source lifetime. The filter preserves your own posts and can preserve items whose relationship status is unavailable. Refreshes can start a new feed lifetime.

The portable build tool is a new integration. Its verification record is in the [recipe](skills/tweakin/references/instagram.md#verification-record). Other app versions and other apps need fresh inspection and phone acceptance. There is no universal switch that removes a feature from an arbitrary app.

## Develop

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_public.py
python3 skills/tweakin/scripts/instagram.py compile --output /tmp/InstagramFocus.dylib
```

The content check audits Git's staged files against an explicit distribution list. The tests use synthetic apps and require no Apple account or Instagram download. See [CONTRIBUTING.md](CONTRIBUTING.md) for adding recipes.

The project uses GPL-3.0-only, with fishhook under its included BSD license. See [source attribution](skills/tweakin/THIRD_PARTY_NOTICES.md). Instagram's application code is supplied separately. This project is not affiliated with Meta or Apple.
