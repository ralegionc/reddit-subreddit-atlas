# Data

This repository does not carry its raw inputs. The files listed below were present locally when the results in the README were produced, and were deleted on 2026-10-12 to reclaim **92.38 MB** of disk. Every one of them is a download from a public upstream source, so nothing unique was lost.

This file exists so that a re-download can be *checked* rather than assumed to match. It records the exact inventory, not just the source.

Upstream sources, with links and licences, are in the README under **Data source**.

## What was removed

92.38 MB in 9618 files.

| Path | Size | Files |
|---|---|---|
| `data/raw` | 92.38 MB | 9618 |

## Restoring it

Author comment histories and subreddit metadata from the Reddit API. Every stage is resumable, so this refills incrementally. `data/raw/seeds.json` is tracked and pins which subreddits the run started from. Expect drift: Reddit is live.

## Inventory

`data_manifest.csv` carries every file with its exact byte length and a fingerprint. Files of 32 MiB or less have a full `sha256`. Larger files have `headtail256`: a sha256 over the first mebibyte, the last mebibyte and the exact byte length, which catches a truncated or altered download without rereading gigabytes.

The 40 largest of 9618 files; `data_manifest.csv` has them all.

| File | Size | Fingerprint |
|---|---|---|
| `data/raw/profiles.jsonl` | 31.99 MB | `sha256:39169e099782e8f095b7f67c57282fd49fcb858ee745ca27c90829ed4f806389` |
| `data/raw/profiles_temporal.jsonl` | 28.98 MB | `sha256:bd57b12af6ed28c4cf234e868db90303c4faf770fc1d2a5d166cec366da99162` |
| `data/raw/subreddit_meta.jsonl` | 796.04 KB | `sha256:09e718b8364fa71213e45d516465a5df163b5f388e4226faae8921fece1d5fb7` |
| `data/raw/authors/AskReddit.json` | 60.39 KB | `sha256:66857618754c023d56b437e0a25cef63514fa125022518d72aae4b5af08c792e` |
| `data/raw/authors/movies.json` | 53.84 KB | `sha256:70be8c4718b60891d0d193813f8087320efc248000d579e0e3ed11e85f4a64bc` |
| `data/raw/authors/todayilearned.json` | 53.55 KB | `sha256:8c418d2bad8c0149d66dd916d3d23dabeedd33a1fec0c9910e8456ec542afb77` |
| `data/raw/authors/funny.json` | 52.14 KB | `sha256:33dff9708e56b67dd7161fa44275f915278aa9923bfd6f529bbc35f0cf4c50da` |
| `data/raw/authors/memes.json` | 51.27 KB | `sha256:e11f4900d573434933cbf1fa7d6cf48c3bb37a3c82652112bd53ad49ed01ee42` |
| `data/raw/authors/gaming.json` | 51.04 KB | `sha256:8d07d4042edd88a85960e9821930dd513fccc5631a6ae3848ac26432e79535ca` |
| `data/raw/authors/nottheonion.json` | 50.72 KB | `sha256:6eebc153f3840ab955c16dcd5e14f7663ccbfa7e3d55fa6b252fce6369bc9ca4` |
| `data/raw/authors/Music.json` | 50.22 KB | `sha256:75384b6feb8cc864fb9c23cffb094673840ba1015f54013af2c845d5d562b87d` |
| `data/raw/authors/books.json` | 47.26 KB | `sha256:083ef8c723febc86ca8ba2175f4a5b174715e9e352412c6c22fe016deccb13c1` |
| `data/raw/authors/videos.json` | 47.02 KB | `sha256:f9219e207eacaf32a50614678112f69492a4b51ddb1925df48a873c025689d48` |
| `data/raw/authors/aww.json` | 46.34 KB | `sha256:df936d65dad4ebc6384293c2b79289fcd88f0db496356105b52662f5650e142c` |
| `data/raw/authors/Jokes.json` | 46.14 KB | `sha256:4a99c2557a7b9e57efd5d00c3f59a2943147a575ed5998aaf0f6b909d4297609` |
| `data/raw/authors/worldnews.json` | 45.46 KB | `sha256:7122e54dd3466a353538032a9f335108176375f06a20df347076c0b841e33fad` |
| `data/raw/authors/DIY.json` | 44.88 KB | `sha256:c784c200bc12f93c63e8653a6bdfdc67c1f1ba8d4dc415763ac091be2d9e3d36` |
| `data/raw/authors/news.json` | 41.91 KB | `sha256:11c8b8e295fc5e25b31b67ffd0aa1810c6f0f70cc587011e4a9479a9f1130347` |
| `data/raw/authors/pics.json` | 40.83 KB | `sha256:fe82f283c1b789e09958130b7fb9fec0d5f8c6600a1c969a79f8ef0ad66e568e` |
| `data/raw/authors/science.json` | 38.97 KB | `sha256:feed0da27bae7d7344a1aec44841cf90c5b8e2da79912e84cdb38bae1c96fb6c` |
| `data/raw/authors/space.json` | 37.78 KB | `sha256:bea6d4603ae042f2aa35e99bc78deab2bd1bfc3c5b341aeee29a89654aaeb43f` |
| `data/raw/authors/Showerthoughts.json` | 26.77 KB | `sha256:ae14995c10b50a47e5ad4d6a649bdfcb377495e2ccf5728fe32e80493e438fde` |
| `data/raw/authors/askscience.json` | 23.43 KB | `sha256:a05fb2439d5f798dd3f32cf9b5dfb7dbd84f345c673a1e3e94232633ab97a538` |
| `data/raw/authors/AITAH.json` | 10.70 KB | `sha256:92f85118d327e1fdfe4dad0e1b57a64d1248523ca74ecc197b05babeea392ad5` |
| `data/raw/authors/NoStupidQuestions.json` | 10.66 KB | `sha256:66603184e6f215545528a1d8702a0855559d0f92344416818d7cd3bfbb1cf030` |
| `data/raw/authors/mildlyinfuriating.json` | 10.51 KB | `sha256:f310cb1cfad9329aa3fd13de6fea2f4aaaea3f0b06beb392678d7232ebca0da9` |
| `data/raw/authors/Damnthatsinteresting.json` | 10.46 KB | `sha256:5ed9b82af2e78bc2f1524d576f39c50777bdf0c182721a73e527cddc239ae536` |
| `data/raw/authors/AbsoluteUnits.json` | 10.38 KB | `sha256:f2f4b08cf9c458871b6e906b737a9b7db28e75fe105589685ca85ff8ea7b0250` |
| `data/raw/authors/BeAmazed.json` | 10.30 KB | `sha256:e3cab70545e14be2224f5f1f508b384e0274b0081f5f177f27d7df0ea62994e5` |
| `data/raw/authors/maybemaybemaybe.json` | 10.26 KB | `sha256:57ee7f47bd7edf8bc535b068130eb8dcd639afd28d12a6da6acbee847982bae2` |
| `data/raw/authors/oddlysatisfying.json` | 10.19 KB | `sha256:d12415ac6d146bb68c0faccc11993a3cd9cea4e2a0d49f501993e32ca5712a12` |
| `data/raw/authors/Satisfyingasfuck.json` | 10.16 KB | `sha256:c79665e44ec5b838ebc494c202ed66ce6ae4202226dfaf6e25d2020097b6180d` |
| `data/raw/authors/StupidFood.json` | 10.15 KB | `sha256:a17924644c2b4fc15709718a9b6b0891e9547c8fa01809177a306dd3f061dc54` |
| `data/raw/authors/blackmagicfuckery.json` | 10.14 KB | `sha256:03ba6873a493e5c40d64e1c2ad4d81dcd6e42ff82fc937ad21aa4044db466a9a` |
| `data/raw/authors/Wellthatsucks.json` | 10.14 KB | `sha256:2ca6373cd9a830979b640c846228b2345afd690c7efce3240405c5f69fc75378` |
| `data/raw/authors/cats.json` | 10.13 KB | `sha256:8611a9d7e8c46f78792e31852ea6922eaa580f3d6b7bc4bb747dbff2ec1e442b` |
| `data/raw/authors/Cooking.json` | 10.12 KB | `sha256:45bfb63866a819a6e737924078f1e9ef56a86bff854fe9c433add5d3d5b554b1` |
| `data/raw/authors/JustGuysBeingDudes.json` | 10.05 KB | `sha256:452131047c58a1b71641a14e245e629d321d517dcdff53226e8e31908498dfdf` |
| `data/raw/authors/politics.json` | 10.05 KB | `sha256:a3d1f2c776af165924672aaa0fb4ae54c2c438d043d224cdc0943482add70517` |
| `data/raw/authors/Bossfight.json` | 10.04 KB | `sha256:cec2c910d57f0fea2be7917b68b1582d39d615ef3f26da8b38b8125e2b185df3` |

A source that is live rather than a fixed release will not reproduce these fingerprints. Where that applies it is said above.

