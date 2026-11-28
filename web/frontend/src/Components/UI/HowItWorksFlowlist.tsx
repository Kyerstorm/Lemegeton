"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { motion, useInView } from "motion/react";
import { Icon } from "../Icons";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface FlowlistItem {
  id: string | number;
  title: string;
  description: string;
}
export interface FlowlistProps {
  items?: FlowlistItem[];
  onItemSelect?: (item: FlowlistItem, index: number) => void;
  showGradients?: boolean;
  enableArrowNavigation?: boolean;
  className?: string;
  listClassName?: string;
  initialSelectedIndex?: number;
  ariaLabel?: string;
}

const defaults: FlowlistItem[] = [
  { id: 1, title: "01 / Interaction", description: "A member starts a command or component interaction." },
  { id: 2, title: "02 / Dispatch", description: "discord.js routes the interaction through the command registry." },
  { id: 3, title: "03 / Domain logic", description: "A helper applies the requested feature operation." },
  { id: 4, title: "04 / Source & storage", description: "Provider data and persisted records keep their provenance." },
  { id: 5, title: "05 / Response", description: "Discord receives the result or the next interaction." },
];

function FlowlistItemView({ item, index, selected, onSelect }: {
  item: FlowlistItem; index: number; selected: boolean; onSelect: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const inView = useInView(ref, { margin: "0px 0px -20px 0px", amount: .35 });
  const reducedMotion = useReducedMotion();
  return (
    <motion.button ref={ref} type="button" className={"hiw-flowlist-item " + (selected ? "is-selected" : "")}
      onClick={onSelect} aria-pressed={selected}
      initial={reducedMotion ? false : { opacity: 0, scale: .94 }}
      animate={{ opacity: inView || reducedMotion ? 1 : .35, scale: inView || reducedMotion ? 1 : .97 }}
      whileHover={reducedMotion ? undefined : { scale: 1.012 }}
      whileTap={reducedMotion ? undefined : { scale: .985 }}
      transition={{ type: "spring", stiffness: 260, damping: 24, delay: reducedMotion ? 0 : .035 }}>
      <span className="hiw-flowlist-number">{String(index + 1).padStart(2, "0")}</span>
      <span className="hiw-flowlist-copy"><strong>{item.title}</strong><small>{item.description}</small></span>
      <Icon name="chevron-right" size={15} />
    </motion.button>
  );
}

export function Flowlist({
  items = defaults,
  onItemSelect,
  showGradients = true,
  enableArrowNavigation = true,
  className = "",
  listClassName = "hiw-flowlist-scroll",
  initialSelectedIndex = -1,
  ariaLabel = "System flow steps",
}: FlowlistProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(initialSelectedIndex);
  const [topFade, setTopFade] = useState(0);
  const [bottomFade, setBottomFade] = useState(1);
  const reducedMotion = useReducedMotion();

  const handleScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    setTopFade(Math.min(element.scrollTop / 50, 1));
    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
    setBottomFade(element.scrollHeight <= element.clientHeight ? 0 : Math.min(remaining / 50, 1));
  }, []);

  useEffect(() => { handleScroll(); }, [handleScroll, items.length]);

  const select = (index: number) => {
    const bounded = Math.max(0, Math.min(index, items.length - 1));
    if (items.length === 0) return;
    setSelectedIndex(bounded);
    onItemSelect?.(items[bounded], bounded);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!enableArrowNavigation || items.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      select(selectedIndex < 0 ? 0 : selectedIndex + (event.key === "ArrowDown" ? 1 : -1));
    }
  };

  useEffect(() => {
    if (selectedIndex < 0 || !scrollRef.current) return;
    const container = scrollRef.current;
    const selected = container.querySelector<HTMLButtonElement>('[data-index="' + selectedIndex + '"]');
    if (!selected) return;
    const margin = 32;
    if (selected.offsetTop < container.scrollTop + margin) {
      container.scrollTo({ top: selected.offsetTop - margin, behavior: reducedMotion ? "auto" : "smooth" });
    } else if (selected.offsetTop + selected.offsetHeight > container.scrollTop + container.clientHeight - margin) {
      container.scrollTo({ top: selected.offsetTop + selected.offsetHeight - container.clientHeight + margin, behavior: reducedMotion ? "auto" : "smooth" });
    }
  }, [selectedIndex, reducedMotion]);

  return (
    <div className={"hiw-flowlist " + className}>
      <div ref={scrollRef} className={listClassName} onScroll={handleScroll} onKeyDown={onKeyDown}
        role="list" aria-label={ariaLabel} tabIndex={0}>
        {items.map((item, index) => (
          <div role="listitem" data-index={index} key={item.id}>
            <FlowlistItemView item={item} index={index} selected={selectedIndex === index} onSelect={() => select(index)} />
          </div>
        ))}
      </div>
      {showGradients ? <>
        <div className="hiw-flowlist-fade hiw-flowlist-fade-top" style={{ opacity: topFade }} />
        <div className="hiw-flowlist-fade hiw-flowlist-fade-bottom" style={{ opacity: bottomFade }} />
      </> : null}
    </div>
  );
}
