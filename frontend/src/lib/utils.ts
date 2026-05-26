/**
 * Provides the `cn` class-name helper used throughout the UI. It merges conditional
 * clsx inputs and resolves conflicting Tailwind classes via tailwind-merge.
 */
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
