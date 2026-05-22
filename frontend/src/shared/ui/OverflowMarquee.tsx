import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

type OverflowMarqueeProps = {
  children: ReactNode;
  className?: string;
  title?: string;
};

/** Horizontally scrolls overflowing single-line content; static when it fits. */
export function OverflowMarquee({ children, className, title }: OverflowMarqueeProps) {
  const outerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLSpanElement>(null);
  const [scrolls, setScrolls] = useState(false);

  const measure = useCallback(() => {
    const outer = outerRef.current;
    const track = trackRef.current;
    if (!outer || !track) return;

    const distance = track.scrollWidth - outer.clientWidth;
    if (distance > 1) {
      outer.style.setProperty('--overflow-marquee-distance', `${distance}px`);
      const durationSec = Math.min(24, Math.max(5, distance / 28));
      outer.style.setProperty('--overflow-marquee-duration', `${durationSec}s`);
      setScrolls(true);
    } else {
      outer.style.removeProperty('--overflow-marquee-distance');
      outer.style.removeProperty('--overflow-marquee-duration');
      setScrolls(false);
    }
  }, []);

  useLayoutEffect(() => {
    measure();
    const outer = outerRef.current;
    const track = trackRef.current;
    if (!outer) return undefined;

    const ro = new ResizeObserver(measure);
    ro.observe(outer);
    if (track) ro.observe(track);
    return () => ro.disconnect();
  }, [measure, children]);

  const classes = ['overflow-marquee', scrolls && 'overflow-marquee--scroll', className]
    .filter(Boolean)
    .join(' ');

  return (
    <div ref={outerRef} className={classes} title={title}>
      <span ref={trackRef} className="overflow-marquee__track">
        {children}
      </span>
    </div>
  );
}
