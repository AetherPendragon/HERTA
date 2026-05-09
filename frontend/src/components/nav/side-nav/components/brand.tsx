export default function Brand() {
  return (
    <div className="flex h-16 items-center border-b border-border px-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary font-mono text-base font-bold text-primary-foreground">
          H
        </div>
        <div>
          <div className="font-mono text-sm font-bold tracking-wider">HERTA</div>
          <div className="text-[10px] text-muted-foreground tracking-wide">Protocol Generator</div>
        </div>
      </div>
    </div>
  );
}
