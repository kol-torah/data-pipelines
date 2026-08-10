"""One-off lookup: print every playlist for a channel handle, so real playlist ids
can be read off by hand. See documents/plans/adapters-plan.md §7.1.

Run with: uv run python -m data_pipelines.adapters.list_youtube_playlists <handle>
(handle without the leading '@')
"""

import argparse

from data_pipelines.adapters.youtube_api import list_channel_playlists, resolve_channel_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handle")
    args = parser.parse_args()

    channel_id = resolve_channel_id(args.handle)
    print(f"@{args.handle} -> channel {channel_id}")
    for playlist in list_channel_playlists(channel_id):
        print(f"{playlist.id}  {playlist.title}")


if __name__ == "__main__":
    main()
