import { useDialogFocus } from "../Hooks/useDialogFocus";
import { Icon } from "../Icons";
import { LogoTraceLoader } from "../UI/LogoTraceLoader";

export function ReceiptThankYou({ onContinue }: { onContinue: () => void }) {
  const dialogRef = useDialogFocus(true, ".thank-you-footer button", onContinue);

  return (
    <div
      ref={dialogRef}
      className="thank-you-page"
      role="dialog"
      aria-modal="true"
      aria-labelledby="thank-you-title"
    >
      <div className="thank-you-shell">
        <header className="thank-you-header">
          <div className="thank-you-brand">
            <span className="thank-you-brand-mark"><LogoTraceLoader size={25} strokeWidth={12} loading={false} isComplete ariaLabel="Lemegeton logo" /></span>
            <span>
              <strong>LEMEGETON</strong>
              <small>COMMUNITY / CONTROL PLANE</small>
            </span>
          </div>
          <span className="thank-you-reference">NOTE / 001</span>
        </header>

        <section className="thank-you-machine" aria-labelledby="thank-you-title">
          <div className="thank-you-machine-header">
            <span>LEMEGETON / MESSAGE PRINTER</span>
            <span>01</span>
          </div>

          <div className="thank-you-screen">
            <span className="thank-you-screen-label">A MESSAGE FOR YOU</span>
            <h1 id="thank-you-title">Thank you.</h1>
            <span className="thank-you-screen-status">
              <Icon name="check-circle" size={15} />
              NOTE COMPLETE
            </span>
          </div>

          <div className="thank-you-printer-slot" aria-hidden="true" />

          <div className="thank-you-paper-wrap">
            <article className="thank-you-paper">
              <p className="thank-you-paper-kicker">LEMEGETON / A SMALL NOTE</p>
              <div className="thank-you-paper-rule" />
              <h2>THANK<br />YOU.</h2>
              <p className="thank-you-paper-copy">
                For being part of the communities that make discovery, creativity
                and shared interests worth coming back to.
              </p>
              <div className="thank-you-paper-rule" />
              <div className="thank-you-paper-meta">
                <span>MADE FOR COMMUNITIES</span>
                <span>WITH APPRECIATION</span>
              </div>
              <p className="thank-you-paper-foot">DISCOVER / CREATE / CONNECT</p>
            </article>
          </div>

          <div className="thank-you-machine-footer">
            <span>LEMEGETON</span>
            <span>END OF NOTE</span>
          </div>
        </section>

        <footer className="thank-you-footer">
          <button className="button primary" type="button" onClick={onContinue}>
            Continue <Icon name="arrow-up-right" size={14} />
          </button>
          <p>Made for the communities that bring it to life.</p>
        </footer>
      </div>
    </div>
  );
}
