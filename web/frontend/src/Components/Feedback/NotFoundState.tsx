import { BrandMark } from "../Brand/BrandMark";
import { Icon } from "../Icons";
export default function NotFoundState() {
 return <main className="login-wrap"><section className="login-card" aria-labelledby="not-found-title">
  <a className="brand login-brand" href="/" aria-label="Lemegeton dashboard home"><BrandMark/><span className="brand-copy"><strong>LEMEGETON</strong><small>CONTROL PLANE</small></span></a>
  <div className="login-kicker"><span className="signal-dot"/> ROUTE / 404 <span className="braille-mini" aria-hidden="true">⠿⠗⠿⠿⠿</span></div>
  <h1 id="not-found-title">This page<br/><span>isn't here.</span></h1>
  <p className="login-copy">The address may be outdated, the page may have moved, or this route may not exist.</p>
  <a className="button primary login-button" href="/">Return to dashboard <Icon name="home" size={16}/></a>
  <div className="login-foot"><span>LEMEGETON / 404</span><span>ROUTE NOT FOUND</span></div>
 </section></main>;
}
