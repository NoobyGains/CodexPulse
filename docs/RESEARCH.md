# CodexPulse integration research

Verified 13 September 2026 against the installed Codex CLI 0.154.0, its generated app-server JSON schemas, official documentation, and read-only live API calls.

## Source project

- GitHub source: `https://github.com/NoobyGains/claude-pulse`
- Remote HEAD at adaptation: `6503e91b007c3011b18844eb76eacf8bfbf86067` (3.3.0 tree).
- Existing local checkout: `85cc0fb` on `release/3.4.0`, with fifteen improved palettes. It differed from remote main rather than being a simple older snapshot. Palette definitions were carried across explicitly; the old project was not edited.
- The new repository retains upstream history and the Source Available license. Its active files contain the Codex implementation, installers, tests, and Codex documentation. It does not install or execute the old Claude status script.

## Integration decisions

1. `tui.status_line` is a list of built-in item identifiers. The native footer can show usage, context, model/reasoning, Git information and other supported built-ins. There is no documented arbitrary-command status renderer. Full Pulse rendering therefore belongs in a dedicated terminal pane. [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
2. `account/rateLimits/read` returns both a backward-compatible single bucket and a map of buckets. Window duration determines session/weekly labeling, not the `primary`/`secondary` slot. Actual live responses included a weekly primary window and additional model quotas. Read operations do not submit model prompts. [App-server rate limits](https://learn.chatgpt.com/docs/app-server)
3. `thread/list` with an exact `cwd` filter and `updated_at` sorting selects a project session; `thread/read` pins an explicit ID without resuming it. Only metadata is requested. [Thread read/list API](https://learn.chatgpt.com/docs/app-server)
4. Existing CLI sessions persist `event_msg/token_count` metadata in local rollout files, including paginated-history sessions in the tested version. Latest token usage and context-window size provide context pressure; cumulative counts provide throughput and cache share. The path and rollout schema are unstable. Parsing is bounded and incremental, and prompt/tool-output content is discarded. Missing values are not reconstructed from assumed model capacities.
5. `account/usage/read` supplies account token activity and, for supported routes, estimated thread cost. Pulse does not substitute Claude pricing or invent subscription dollar costs. Currency conversion uses a user-specified rate. [Account activity API](https://learn.chatgpt.com/docs/app-server)
6. Native installation uses `config/value/write` to preserve TOML structure, with a private local original-config backup and a post-install checksum. Uninstall restores only if no later edits would be overwritten.
7. The native footer reports remaining quota; the companion reports used quota. This difference is explicit in the README and helper skill.

## Primary implementation references

- [Official Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Official Codex app-server documentation](https://learn.chatgpt.com/docs/app-server)
- [OpenAI's status-line item implementation](https://github.com/openai/codex/blob/main/codex-rs/tui/src/bottom_pane/status_line_setup.rs)
- Local CLI-generated schemas from `codex app-server generate-json-schema`, including `GetAccountRateLimitsResponse`, `ThreadReadResponse`, `ThreadTokenUsageUpdatedNotification`, `GetAccountTokenUsageResponse`, and `ConfigValueWriteParams`.

## Deliberate boundaries

Claude hooks, Anthropic OAuth, model pricing tables, per-agent status-line injection, fabricated spawn budgets, and Claude auto-update logic are not routed into Codex. The README contains the feature-by-feature differences. Public artwork uses synthetic data; private local cache, research captures, and runtime metadata are ignored by Git.
