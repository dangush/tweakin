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

With ipatool 2.8.1, passing `--bundle-identifier` to `list-versions` failed with `failed to resolve the country code: available storefronts request failed`, while the same command with only `--app-id 389801252` succeeded. The listing returned about 830 identifiers in ascending release order. Querying metadata for one identifier at a time and bisecting by display version located 418.2.0 in about ten requests:

```sh
ipatool list-versions --app-id 389801252 --platform iphone --format json
ipatool get-version-metadata --app-id 389801252 --platform iphone \
  --external-version-id CANDIDATE_ID --format json
```

In that run, identifier `882750070` returned display version `418.2.0` with release date 2026-02-27. Treat it as a starting candidate and confirm the metadata yourself before downloading.

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

UnfairPlay is a Go program. Install a Go toolchain at least as new as the `go` directive in its `go.mod` (1.26 at the original commit) and build it with `go build -o unfairplay ./cmd/unfairplay` from its checkout.

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

Setup prints progress to standard error and its JSON result to standard output, so redirect standard output to a private file such as `"$work/unfairplay-setup.json"`. Check `success`, `plaintext_verified`, and `validation_source` there without pasting the file elsewhere. The Mac App Store account that installed the validation app must be the account that downloaded the IPA. In the accepted run, a small unrelated iPhone app validated the model and the Instagram decryption reported `PlaintextVerified` for all 14 encrypted images. The decrypted IPA was smaller than the download because of archive compression and the stripped licenses; its uncompressed contents differed only by the removed licensing files.

The saved model contains private decryption material tied to your Store enrollment. Keep it on machines you control. Never put it in this repository, send it to a friend, or attach it to an issue. Follow [UnfairPlay's own use and licensing instructions](https://github.com/DrWhax/unfairplay#legal-and-ethical-use).

## Pass the input to the recipe

Run the Instagram recipe's inspection command against the decrypted IPA. Confirm the exact bundle and version and check all retained images for encryption. The build tool independently rejects encrypted retained images. Acquisition consistency alone does not prove that the native hooks work.
