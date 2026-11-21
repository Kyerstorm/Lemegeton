import { BrandMark } from "../Brand/BrandMark";
import { Icon } from "../Icons";
export interface ErrorStateProps { title?:string; description?:string; onRetry?:()=>void; }
export function ErrorState({title="Something went wrong.",description="The dashboard couldn't complete this request. Your saved configuration has not been changed.",onRetry}:ErrorStateProps) {
 return <main className="login-wrap"><section className="login-card" aria-labelledby="dashboard-error-title" role="alert">
  <a className="brand login-brand" href="/" aria-label="Lemegeton dashboard home"><BrandMark/><span className="brand-copy"><strong>LEMEGETON</strong><small>CONTROL PLANE</small></span></a>
  <div className="login-kicker"><span className="signal-dot"/> SYSTEM / RECOVERY</div>
  <h1 id="dashboard-error-title">{title}</h1><p className="login-copy">{description}</p>
  {onRetry?<button className="button primary login-button" type="button" onClick={onRetry}>Try again <Icon name="retry" size={16}/></button>:null}
  <a className="signout" href="/">Return to dashboard <Icon name="home" size={16}/></a>
  <div className="login-foot"><span>LEMEGETON / RECOVERY</span><span>NO CHANGE APPLIED</span></div>
 </section></main>;
}
