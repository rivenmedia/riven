import manualScrapeModalTemplate from "../../../src/templates/components/manual_scrape_modal.html?raw";

export default function LegacyScaffold() {
  return (
    <div
      aria-hidden="true"
      style={{ display: "none" }}
      dangerouslySetInnerHTML={{ __html: manualScrapeModalTemplate }}
    />
  );
}
