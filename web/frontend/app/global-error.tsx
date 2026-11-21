"use client";
import { GlobalStyles } from "../src/DesignSystem/GlobalStyles";
import { ErrorState } from "../src/Components/Feedback/ErrorState";
export default function GlobalError({reset}:{error:Error & {digest?:string};reset:()=>void}) {
 return <html lang="en"><body><GlobalStyles /><ErrorState title="The dashboard is unavailable." description="An unexpected application error interrupted this page. You can retry or return to the dashboard." onRetry={reset}/></body></html>;
}
