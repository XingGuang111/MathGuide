# Interactive pet animation provenance

These nine transparent WebM clips are imported from the animation set in [`PC2005-cloud/dsh-pet`](https://github.com/PC2005-cloud/dsh-pet), pinned to commit `ad9e2cb50348280634021e0699482f43b56ce1ca`.

The upstream MIT code license is bundled as `LICENSE.txt`. Its README separately restricts commercial use of the character/animations; see `ASSET-NOTICE.md` and the pinned `UPSTREAM-README.md`. The files are used by MathGuide as browser playback assets:

| Local clip | Upstream action | Use in MathGuide |
|---|---|---|
| `idle.webm` | 待机呼吸休闲 | 默认陪伴 |
| `touch.webm` | 点击回应-开心跃动 | 点击摸摸 |
| `wave.webm` | 点击回应-元气挥手 | 拖动后回应 |
| `drag.webm` | 被鼠标拖拽悬空反馈 | 拖动中 |
| `eat.webm` | 大口吃零食 | 投喂 |
| `play.webm` | 三球抛接 | 玩彩虹小球 |
| `think.webm` | 工作状态-思考冒泡 | 辅导进行中 |
| `celebrate.webm` | 工作状态-雀跃庆祝 | 完成任务 |
| `sleep.webm` | 原地小憩沉眠 | 长时间无操作 |

The five `expression-*.svg` facial overlays and CSS tear, bounce and sway effects are original MathGuide artwork, aligned to a still frame of the licensed `idle.webm` character. They provide smile, laughter, concern, tears and pleading without additional downloaded clips or independently modeled expressions. Interactive actions still play the original nine clips. Runtime playback uses local files only.

The four original SVG food and toy icons under `web/assets/items/` are MathGuide illustrations. The legacy PNGs directly under `items/shop/` are derived from upstream animation frames and retain the upstream asset terms. Current shop illustrations under `items/shop/illustrated/` are original object-only vector drawings exported to PNG; their editable SVGs and source notice are retained in that directory.

## Additional learnable clips

Nine additional local WebM files follow the source list in
`youxin484/dsh-dafeiyu-enhanced` at commit
`e4006c754b40570ddaa8bb5d2d1ed16cdd2e8af2` (`assets/pet-manifest.json`).
That plugin pins its whale-tail character to `PC2005-cloud/dsh-pet`
commit `549fff2ea33c2acfb16612c76912c6137da4a758`. MathGuide imports the
original WebM clips rather than the plugin's converted WebP frames.
Every local file was checked against the plugin manifest's source SHA-256;
`tricks.json` records each source filename, version, and hash. The upstream asset notice applies to these clips; `LICENSE.txt` alone describes the code license. No restricted legacy BigFish
character assets are included. No plugin runtime source code is copied.

| Local clip | Original action |
|---|---|
| `stretch.webm` | 超大伸懒腰 |
| `giggle.webm` | 点击回应-挠痒咯咯笑 |
| `bubbles.webm` | 鲸鱼吐泡泡特效 |
| `scout.webm` | 工作状态-原地踱步张望 |
| `busy.webm` | 工作状态-忙碌点按 |
| `sort.webm` | 工作状态-清点归档 |
| `token.webm` | 吃Token |
| `yawn.webm` | 哈欠连天 |
| `sigh.webm` | 工作状态-垂头叹气冒汗 |

The three hat designs under `web/assets/hats/` are original MathGuide SVG
artwork. Their `-worn.svg` counterparts position the same artwork over the
licensed character. `hat-tracks.json` contains locally sampled face position
offsets for approximate attachment during motion, generated using
`tools/build_pet_hat_tracks.py`; it is not an upstream animation or rig.

## Food and toy shop clips

`shop-manifest.json` records 25 additional original WebM clips (18 food and 7 toy animations), pinned to `ad9e2cb50348280634021e0699482f43b56ce1ca`. Each was verified against its pinned Git blob SHA and a local SHA-256. The character bubble snack reuses the already imported `token.webm`, giving 19 new foods in total. `pet_shop.py` maps each physical item to its specific animation. The 256-pixel transparent shop previews in `../items/shop/` are actual stills, extracted with `tools/build_pet_shop_previews.py`. Hat attachment offsets for these actions were sampled locally. Both the original videos and derived previews are subject to the upstream asset restrictions in `ASSET-NOTICE.md`. No DSH runtime code or external package is installed.

## More play lessons

17 play animations from the upstream 玩耍 collection are pinned to
`ad9e2cb50348280634021e0699482f43b56ce1ca`. `tricks.json` records each original
filename, commit, Git blob and SHA-256. These include flute, violin, three dances,
dove/card/flower magic, juggling, shuttlecock, gomoku, petting a cat, animals,
butterflies, whale, opening a gift and jumping to catch an object. They retain
the non-commercial asset terms in `ASSET-NOTICE.md`. Hat offsets are sampled
locally for each clip; the original videos are unchanged.
