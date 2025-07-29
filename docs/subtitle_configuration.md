# Subtitle Configuration

## Downloading Multiple Subtitles Per Language

Riven now supports downloading multiple subtitle files per language, giving you more options to choose from. This is useful when:

- You want backup options if the primary subtitle has issues
- Different family members prefer different subtitle styles
- You need both regular and hearing-impaired (SDH) versions
- Subtitle quality varies between providers

### Configuration

Add the `count_per_language` setting to your subtitle configuration:

```json
{
  "post_processing": {
    "subliminal": {
      "enabled": true,
      "languages": ["eng", "heb", "jpn"],
      "count_per_language": 2,  // Number of subtitles to download per language
      "providers": {
        "opensubtitles": {
          "enabled": false,
          "username": "",
          "password": ""
        },
        "opensubtitlescom": {
          "enabled": false,
          "username": "",
          "password": ""
        }
      }
    }
  }
}
```

### Settings Explained

- **`languages`**: List of language codes to download (e.g., "eng" for English, "heb" for Hebrew)
- **`count_per_language`**: Number of subtitles to download for each language (default: 1)
  - Set to 1 to maintain the original behavior (one subtitle per language)
  - Set to 2 or more to download multiple options per language

### File Naming

When downloading multiple subtitles per language, files are named as follows:

- First subtitle: `movie_name.{language}.srt` (e.g., `movie_name.eng.srt`)
- Additional subtitles: `movie_name.{language}.{number}.srt` (e.g., `movie_name.eng.2.srt`, `movie_name.eng.3.srt`)

### Example

With this configuration:
```json
{
  "languages": ["eng", "spa"],
  "count_per_language": 3
}
```

You might get:
- `The.Matrix.1999.eng.srt` (best match)
- `The.Matrix.1999.eng.2.srt` (second best)
- `The.Matrix.1999.eng.3.srt` (third best)
- `The.Matrix.1999.spa.srt` (best Spanish match)
- `The.Matrix.1999.spa.2.srt` (second best Spanish)
- `The.Matrix.1999.spa.3.srt` (third best Spanish)

### Selection Criteria

Subtitles are ranked and selected based on:
1. Match quality (release group, format, resolution, etc.)
2. Provider ranking
3. User ratings (if available)

The best matches are always downloaded first, with additional subtitles being the next best options available. 