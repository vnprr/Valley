import { Bike, Car, Footprints, type LucideIcon } from "lucide-react";
import type { Transport } from "./api/types";

export const TRANSPORTS: { id: Transport; label: string; Icon: LucideIcon }[] = [
  { id: "walk", label: "pieszo", Icon: Footprints },
  { id: "bike", label: "rower", Icon: Bike },
  { id: "car", label: "samochód", Icon: Car },
];

export const transportInfo = (t: Transport | null) => TRANSPORTS.find((x) => x.id === t) ?? null;
