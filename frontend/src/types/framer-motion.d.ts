import { HTMLMotionProps } from 'framer-motion';
import { HTMLAttributes } from 'react';

declare module 'framer-motion' {
  export interface MotionProps extends HTMLAttributes<HTMLElement> {
    className?: string;
  }
}
