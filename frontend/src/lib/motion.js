// Centralized Framer Motion variants — every page imports from here so the
// whole app shares one easing/timing language instead of hand-rolled
// transitions per component.

export const fadeInUp = {
  hidden:  { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] } },
}

export const scaleIn = {
  hidden:  { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] } },
}

// Stagger the immediate children of whatever this is applied to.
// Cap usage to ~10-15 visible items — beyond that the cumulative trickle-in
// delay hurts scannability more than it adds polish (fade the rest in as one
// unit instead of extending the stagger).
export const staggerContainer = {
  hidden:  { opacity: 1 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.05, delayChildren: 0.03 },
  },
}
