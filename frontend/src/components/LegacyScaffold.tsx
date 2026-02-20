import manualScrapeModalTemplate from "../legacy/templates/manual_scrape_modal.html?raw";

export default function LegacyScaffold() {
  return (
    <div
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: manualScrapeModalTemplate }}
      style={{ display: "none" }}
    />
  );
}
