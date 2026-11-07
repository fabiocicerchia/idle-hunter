@domain:documentation-site @area:brand-palette @from:stylesheets/extra
Feature: Branded, readable documentation site
  Readers of the idle-hunter docs get one consistent brand look in light and dark mode, with legible links, system fonts and no stand-in logo, so the docs and the splash page read as one product.

  Background:
    Given the idle-hunter documentation site is published with its custom stylesheet

  @id:docs.documentation-site.brand-palette.001 @rule:docs.brand.single-accent-palette @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: The docs and the splash page share one accent colour pair
    Given the accent pair is cyan #22d3ee and indigo #6366f1
    When a reader opens the splash page and then the rendered documentation
    Then the documentation's primary colour, and its links in light mode, use indigo #6366f1
    And interactive accents of the documentation use cyan #22d3ee
    And the splash page draws its accents from the same cyan and indigo pair

  @id:docs.documentation-site.brand-palette.002 @rule:docs.themes.legible-links-per-scheme @inferred @source:docs/stylesheets/extra.css#[data-md-color-scheme="slate"]
  Scenario Outline: Links stay readable in both light and dark mode
    Given the reader's colour scheme is <scheme>
    When the reader views a documentation page with a link
    Then links are shown in <link colour>
    And the page background is <background>

    Examples:
      | scheme          | link colour    | background                                                   |
      | light (default) | indigo #6366f1 | the default light background                                 |
      | dark (slate)    | cyan #22d3ee   | near-black #0b0f1a, with header and tabs in the same #0b0f1a |

  @id:docs.documentation-site.brand-palette.003 @rule:docs.typography.system-font-stacks @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: Docs render in the reader's system fonts
    Given the reader's device has its own system and monospace fonts
    When the reader views a documentation page with prose and a code block
    Then prose is set in the system sans-serif stack starting with -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto
    And code is set in the system monospace stack starting with ui-monospace, SFMono-Regular, "SF Mono", Menlo
    And no font file is downloaded to render the page

  @id:docs.documentation-site.brand-palette.004 @rule:docs.offline.no-network-assets @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: The documentation styling loads nothing over the network
    Given the reader is offline or blocks third-party requests
    When the reader opens a documentation page
    Then the page keeps its brand colours and fonts
    And no CDN, web font or analytics request is made by the stylesheet

  @id:docs.documentation-site.brand-palette.005 @rule:docs.navigation.no-stand-in-logo @inferred @source:docs/stylesheets/extra.css#.md-header__button.md-logo
  Scenario: The header shows no generic stand-in logo
    Given the project has no logo configured for the docs
    When the reader views the header and the navigation drawer
    Then no logo icon is shown in the header
    And no logo icon is shown at the top of the navigation drawer
