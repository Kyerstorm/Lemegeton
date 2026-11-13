export const PALETTE={
 PRIMARY:0x7c5cff,
 SECONDARY:0x48567d,
 SUCCESS:0x2ecc71,
 WARNING:0xf1c40f,
 DANGER:0xe74c3c,
 INFO:0x3498db,
 NEUTRAL:0x8291aa,
 PANEL:0x1f273a,
} as const;

export type PaletteState="success"|"ok"|"warning"|"warn"|"error"|"danger"|"failure"|"info"|"neutral"|"secondary"|"panel";

export function colorForState(state:string|undefined|null):number{
 const normalized=(state??"").trim().toLowerCase() as PaletteState;
 return ({
  success:PALETTE.SUCCESS,ok:PALETTE.SUCCESS,
  warning:PALETTE.WARNING,warn:PALETTE.WARNING,
  error:PALETTE.DANGER,danger:PALETTE.DANGER,failure:PALETTE.DANGER,
  info:PALETTE.INFO,neutral:PALETTE.NEUTRAL,
  secondary:PALETTE.SECONDARY,panel:PALETTE.PANEL,
 } as Partial<Record<PaletteState,number>>)[normalized]??PALETTE.PRIMARY;
}
