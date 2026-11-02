/**
 * Shared motion scale for Reanimated (and duration ms for RN Animated).
 * Prefer these over one-off copy-pasted durations/easings.
 */
import { Easing } from "react-native-reanimated";

export { motionMs } from "@/lib/motionDuration";
export { useReduceMotion, useReduceMotionSetting } from "@/lib/reduceMotion";

export const Motion = {
  duration: {
    /** Press feedback */
    press: 100,
    /** Standard screen / chrome transition */
    standard: 180,
    /** Fade / banner enter-exit */
    snappy: 200,
    /** Short UI settle (e.g. stream layout hold) */
    short: 280,
    /** Cursor blink half-cycle */
    pulse: 450,
    /** Skeleton opacity breathe half-cycle */
    breathe: 600,
    /** Soft pulse (typing / mic / image-gen) */
    soft: 700,
    /** Pendulum / sway half-cycle */
    sway: 650,
    /**
     * One trajectory playthrough. Deliberately fixed rather than the real
     * flight time, which ranges from half a second to tens of seconds — a
     * faithful clock would be either over before it registers or unwatchable.
     * The axis states the real time; the animation shows the shape.
     */
    trajectory: 1600,
    /**
     * A scene needs enough time for the user to inspect forces and stop the
     * motion deliberately. Graph playback stays compact; moving bodies use a
     * slower pass because their labels and vectors are part of the lesson.
     */
    simulation: 4000,
  },
  /**
   * Reanimated `withSpring` configs. Popovers grow from their anchor, dialogs
   * settle in the middle, press feedback snaps back. Skip them under Reduce
   * Motion (`useReduceMotion`).
   */
  spring: {
    popover: { damping: 24, stiffness: 340, mass: 0.9 },
    dialog: { damping: 22, stiffness: 300, mass: 1 },
    press: { damping: 18, stiffness: 420, mass: 0.6 },
    /** Clock hand and similar pointers gliding to a new value. */
    pointer: { damping: 20, stiffness: 260, mass: 0.8 },
  },
  easing: {
    inOut: Easing.inOut(Easing.ease),
    sway: Easing.inOut(Easing.sin),
    out: Easing.out(Easing.ease),
    in: Easing.in(Easing.ease),
    /**
     * Constant rate. For a trajectory this is correctness, not laziness: the
     * points are sampled at uniform time steps, so any ease would distort the
     * apparent velocity and make the graph misstate the physics.
     */
    linear: Easing.linear,
  },
} as const;
