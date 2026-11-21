"use client";
import { ErrorState } from "../src/Components/Feedback/ErrorState";
export default function DashboardError({reset}:{error:Error & {digest?:string};reset:()=>void}) {
 return <ErrorState title="The dashboard hit an error." description="This page could not finish rendering. Retry safely; unsaved changes are not reported as saved." onRetry={reset}/>;
}
