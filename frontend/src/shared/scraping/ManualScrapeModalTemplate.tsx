export default function ManualScrapeModalTemplate() {
  return (
    <template id="manual-scrape-modal-tpl">
      <dialog className="modal" data-slot="modal">
        <header>
          <h2>Manual Scrape</h2>
          <button data-action="close">&times;</button>
        </header>
        <div className="modal-body">
          <label>Magnet URL</label>
          <textarea
            data-slot="magnet"
            placeholder="Paste magnet link..."
          ></textarea>
          <button data-action="start-session">Start Session</button>
          <div className="stream-options" data-slot="stream-options"></div>
        </div>
      </dialog>
    </template>
  );
}
