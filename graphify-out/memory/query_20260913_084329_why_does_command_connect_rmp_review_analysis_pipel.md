---
type: "query"
date: "2026-09-13T08:43:29.571204+00:00"
question: "Why does Command connect RMP Review Analysis Pipeline to Scraping & Embedding Management Commands?"
contributor: "graphify"
source_nodes: ["analyze_all_rmp_command", "basecommand"]
---

# Q: Why does Command connect RMP Review Analysis Pipeline to Scraping & Embedding Management Commands?

## Answer

The bridge is Django's BaseCommand: every management command class is named Command and inherits BaseCommand. The Louvain clustering happened to place the shared BaseCommand node in the Scraping & Embedding Management Commands community, so every other command's inherits-edge to it reads as a cross-community bridge. It is a framework-convention artifact, not a deliberate architectural coupling between RMP analysis and scraping/embedding.

## Source Nodes

- analyze_all_rmp_command
- basecommand