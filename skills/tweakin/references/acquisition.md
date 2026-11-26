# Obtain a compatible app copy

Start with an app you acquired through your own account. Keep all downloaded packages, reports, and enrollment models in a private working directory outside the repository. Supply an existing compatible decrypted IPA if you already have one.

```sh
work="$HOME/tweakin-work"
mkdir -p "$work"
chmod 700 "$work"
```

## Download from the App Store

[ipatool](https://github.com/majd/ipatool) authenticates to the App Store and downloads account-personalized packages. The original Instagram workflow used [commit b352566](https://github.com/majd/ipatool/tree/b352566155a667d8aaeabaa7ecec4966080f92ab). Install or build the tool from its upstream instructions and check its local `--help` before using a newer version.

Run authentication in your own Terminal session:

```sh
ipatool auth login
ipatool list-versions --bundle-identifier com.burbn.instagram --platform iphone
```

The Instagram recipe requires display version `418.2.0`. Store version identifiers are separate numeric identifiers. Inspect candidate identifiers using `ipatool get-version-metadata --help` and verify the returned display version before downloading. Availability depends on the Store and your account. If the pinned version is unavailable, stop the recipe and investigate a newly supported version.

If `list-versions` fails with `failed to resolve the country code`, pass only `--app-id 389801252`; this worked with ipatool 2.8.1. Identifiers are listed in release order, so bisect them with `get-version-metadata`. In one run, `882750070` returned `418.2.0`; confirm it before downloading.

Once you have the correct external version identifier:

```sh
ipatool download --app-id 389801252 --platform iphone \
  --external-version-id YOUR_VERIFIED_EXTERNAL_VERSION_ID \
  --purchase --output "$work/Instagram.encrypted.ipa"
```

Complete passwords and verification codes locally. Do not paste account sessions or authentication output into chat or an issue. This download does not require Instagram to be installed on your iPhone.

## Decrypt on your own enrolled Mac

[UnfairPlay](https://github.com/DrWhax/unfairplay) recovers a local FairPlay model and decrypts matching personalized IPAs. It does not download the app or sign the result. The original workflow used [commit d750308](https://github.com/DrWhax/unfairplay/tree/d7503082a59e3dcfdd3ea7a70434dcecaaaf07df). Its current README documents additional workflows, so use the instructions that match your installed revision.

For the original app-based setup, sign into the native Mac App Store, install an eligible iPhone or iPad app on the Mac, and open it once. The installed app must provide the supported encrypted images and licenses for that Mac's Store enrollment. The validation app can be different from Instagram. A USB-connected iPhone does not supply this Mac enrollment.

Build UnfairPlay with `go build -o unfairplay ./cmd/unfairplay`, using a Go toolchain that satisfies its `go.mod`.

With a built `unfairplay` tool, the original command shape is:

```sh
mkdir -p "$work/models"
chmod 700 "$work/models"
sudo ./unfairplay setup --app /Applications/YOUR_INSTALLED_APP.app --model-dir "$work/models"
./unfairplay decrypt --model "$work/models" \
  --input "$work/Instagram.encrypted.ipa" \
  --output "$work/Instagram.decrypted.ipa" --strip-account-data
```

Run `setup --help` and `decrypt --help` first. Enter administrator authentication locally and keep any reports private. Inspect the validation result, including plaintext hash verification when available. A successful model recovery, successful decryption, and verified plaintext are distinct outcomes. Redaction removes account metadata; it does not make an app package suitable for publishing.

Setup writes its JSON result to standard output; redirect it to a private file and check `success` and `plaintext_verified`. The validation app and the IPA must come from the same Store account. A decrypted IPA can be noticeably smaller than the download because of recompression and removed licenses.

The saved model contains private decryption material tied to your Store enrollment. Keep it on machines you control. Never put it in this repository, send it to a friend, or attach it to an issue. Follow [UnfairPlay's own use and licensing instructions](https://github.com/DrWhax/unfairplay#legal-and-ethical-use).

## Pass the input to the recipe

Run the Instagram recipe's inspection command against the decrypted IPA. Confirm the exact bundle and version and check all retained images for encryption. The build tool independently rejects encrypted retained images. Acquisition consistency alone does not prove that the native hooks work.
