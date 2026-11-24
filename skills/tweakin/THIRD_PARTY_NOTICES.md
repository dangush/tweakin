# Source attribution

The Instagram Focus hooks adapt [SCInsta](https://github.com/SoCuul/SCInsta/tree/7bb71807190518ed45d21c716704c38e45a19253), GPL-3.0, at commit `7bb71807190518ed45d21c716704c38e45a19253`. The adapted source includes Reel scrolling and auto-advance controls, Explore hiding, Home suggestion model handling, and the navigation hooks. The followed-author filter, own-post exception, post cap, diagnostics, and packaging integration extend that work. The adapted patch and this project's scripts and documentation are distributed under GPL-3.0-only. The license is included as `LICENSE`.

The included [fishhook](https://github.com/facebook/fishhook/tree/aadc161ac3b80db07a9908851839a17ba63a9eb1) source is commit `aadc161ac3b80db07a9908851839a17ba63a9eb1`, copyright Facebook, Inc. Its BSD license remains at `assets/instagram-focus/src/third_party/fishhook/LICENSE` and in the source headers.

[UnfairPlay](https://github.com/DrWhax/unfairplay/tree/d7503082a59e3dcfdd3ea7a70434dcecaaaf07df) and [ipatool](https://github.com/majd/ipatool/tree/b352566155a667d8aaeabaa7ecec4966080f92ab) are external tools used in the original workflow. Their source and binaries are not included. Follow their own licenses and third-party notices when building or distributing them. The reference commits record the original workflow and are not a claim that those tools' current interfaces are unchanged.

Instagram's executable, assets, personalized licenses, and service implementation are not included. Instagram belongs to Meta. This project is not affiliated with Meta or Apple.
