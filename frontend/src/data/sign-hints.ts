// Per-sign pedagogical hint copy for the pilot lesson group (Req 10).
//
// Two hint surfaces consume this:
//  - `default`: shown when the learner opens the hint BEFORE a failed attempt
//    (a word-tied teachable cue + the reference video the dialog already shows).
//  - the per-parameter strings (handshape/movement/location): used by the
//    rule-based attempt diagnosis (lib/hint-diagnosis.ts) to surface a TARGETED
//    hint AFTER a failed recorded attempt, based on what the learner did.
//
// Keyed by UPPERCASE gloss (matches the model's gloss_to_idx keys + the sign's
// englishGloss.toUpperCase()). Pilot copy: cues are observable/teachable and
// lean on the reference clip; they are not authored sign-linguistics and should
// be reviewed by someone with ASL expertise before classroom use.

export type HintParameter =
  | 'handshape'
  | 'movement'
  | 'location'
  | 'palm-orientation'
  | 'timing'
  | 'framing';

export interface SignHint {
  /** Word-tied default, shown on an unprompted hint open (before any failure). */
  default: string;
  handshape?: string;
  movement?: string;
  location?: string;
}

// PILOT COPY — observable/teachable cues, not authored sign-linguistics; pending ASL-expert review before classroom use.
export const SIGN_HINTS: Record<string, SignHint> = {
  MOM: {
    default: "Open '5' hand, thumb taps the chin. Compare your handshape and chin contact to the reference.",
    handshape: "Use an open '5' hand — all five fingers spread.",
    location: 'Tap the thumb to your chin, not your forehead (that is DAD).',
  },
  DAD: {
    default: "Open '5' hand, thumb taps the forehead. Watch the reference for the handshape and where it lands.",
    handshape: "Open '5' hand, fingers spread.",
    location: 'Thumb touches the forehead — the chin is MOM.',
  },
  BROTHER: {
    default: 'Watch where the reference hand starts near the head and where it ends. Match the start and end points before adding speed.',
    location: 'Notice the hand begins up near the head, not at the chest.',
  },
  GRANDMA: {
    default: 'Like MOM at the chin, then the hand moves outward in arcs. Match the chin start, then mirror the forward arc in the reference.',
    location: 'Start at the chin, then move outward — not at the forehead.',
    movement: 'Add the small forward arcs only after the chin start matches.',
  },
  GRANDPA: {
    default: 'Like DAD at the forehead, then the hand moves outward in arcs. Match the forehead start, then mirror the forward arc.',
    location: 'Start at the forehead, then move outward — not at the chin.',
    movement: 'Add the small forward arcs only after the forehead start matches.',
  },
  AUNT: {
    default: 'A single hand makes a small shape beside the cheek/jaw. Match the handshape and keep it near the lower face as in the reference.',
    location: 'Keep the hand near the cheek/jaw, not center of the face.',
  },
  UNCLE: {
    default: 'A single hand makes a small shape up near the temple/side of the head. Match the handshape and that upper position.',
    location: 'Keep the hand near the temple, higher than AUNT.',
  },
  BOY: {
    default: 'Watch the hand work near the forehead in the reference. Match the handshape and the grasping motion before adding speed.',
    location: 'Keep the action near the forehead.',
    movement: 'Match the small open-close grasp shown in the reference.',
  },
  GIRL: {
    default: 'Watch the thumb trace along the jaw/cheek in the reference. Match the thumb contact and the downward stroke.',
    location: 'Keep the action along the jaw/cheek, lower than BOY.',
    movement: 'Stroke the thumb down along the jawline as in the reference.',
  },
  DOG: {
    default: 'Watch the inviting/snapping gesture in the reference. Copy the hand position and the motion rather than holding still.',
    movement: 'Match the snap or pat motion shown — do not freeze the hand.',
  },
  CAT: {
    default: 'Watch the fingers trace whiskers out from beside the nose/cheek. Match that starting point and the outward stroke.',
    location: 'Start beside the nose/cheek, then stroke outward.',
    movement: 'Pull outward like drawing whiskers, as in the reference.',
  },
  BIRD: {
    default: 'Watch the fingers open and close like a beak near the mouth. Match the location and that pinching motion.',
    location: 'Keep the beak shape at the mouth.',
    movement: 'Open and close the fingers like a beak, as in the reference.',
  },
  FISH: {
    default: 'Watch the flat hand wiggle forward like a swimming fish. Match the flat handshape and the forward wave.',
    handshape: 'Keep the hand flat, fingers together.',
    movement: 'Wiggle the hand forward like a fish swimming.',
  },
  HORSE: {
    default: 'Watch the fingers flick up and down beside the head like an ear. Match that location and the bending motion.',
    location: 'Keep the hand at the side of the head.',
    movement: 'Bend the fingers up and down like a flicking ear.',
  },
  COW: {
    default: 'Watch the thumb anchor at the temple while the hand twists, like a horn. Match the thumb contact and the twist.',
    location: 'Anchor the thumb at the temple.',
    movement: 'Twist the hand from the temple as in the reference.',
  },
  PIG: {
    default: 'Watch the flat hand flap under the chin in the reference. Match the hand-under-chin position and the flapping motion.',
    location: 'Keep the flat hand under the chin.',
    movement: 'Flap the hand down at the chin, as in the reference.',
  },
  DUCK: {
    default: 'Watch the fingers open and close at the mouth like a wide bill. Match the location and the snapping motion.',
    location: 'Keep the bill shape at the mouth.',
    movement: 'Open and close the fingers like a duck bill.',
  },
  FROG: {
    default: 'Watch the hand flick out from under the chin in the reference. Match the under-chin start and the flicking motion.',
    location: 'Start under the chin.',
    movement: 'Flick the fingers outward as in the reference.',
  },
  LION: {
    default: 'Watch the hand sweep back over the head like a mane. Match the over-the-head path shown in the reference.',
    location: 'Move the hand over the top of the head.',
    movement: 'Sweep back over the head like a mane.',
  },
  ELEPHANT: {
    default: 'Watch the hand trace down and out from the nose like a trunk. Match the nose start and the long curving path.',
    location: 'Start at the nose.',
    movement: 'Trace a long curve outward like a trunk.',
  },
  OWL: {
    default: 'Watch the round shapes held at the eyes like big owl eyes. Match the location and keep the shapes at both eyes.',
    location: 'Hold the shapes at both eyes.',
  },
  BEE: {
    default: 'Watch the pinch at the cheek in the reference. Match that location and the small motion rather than holding still.',
    location: 'Keep the action at the cheek.',
  },
  MOUSE: {
    default: 'Watch the finger flick across the nose in the reference. Match the nose location and the brushing motion.',
    location: 'Keep the action at the nose.',
    movement: 'Brush the finger across the nose, as in the reference.',
  },
  RED: {
    default: 'Watch the finger brush down across the lips in the reference. Match the lip contact and the downward stroke.',
    location: 'Brush at the lips.',
    movement: 'Stroke the finger down across the lips.',
  },
  BLUE: {
    default: "Watch the hand shake slightly in neutral space. Match the handshape, then add the small twisting shake.",
    movement: 'Add a small twist/shake, as in the reference.',
  },
  GREEN: {
    default: 'Watch the hand shake slightly in neutral space. Match the handshape, then add the small twisting shake.',
    movement: 'Add a small twist/shake, as in the reference.',
  },
  YELLOW: {
    default: 'Watch the hand shake slightly in neutral space. Match the handshape, then add the small twisting shake.',
    movement: 'Add a small twist/shake, as in the reference.',
  },
  BLACK: {
    default: 'Watch the finger draw across the forehead/brow in the reference. Match that location and the sideways stroke.',
    location: 'Draw across the brow.',
    movement: 'Stroke sideways across the forehead.',
  },
  WHITE: {
    default: 'Watch the hand start on the chest and pull outward while the fingers close. Match the chest start and that motion.',
    location: 'Start on the chest.',
    movement: 'Pull outward as the fingers draw together.',
  },
  BROWN: {
    default: 'Watch the hand slide down along the cheek in the reference. Match the cheek contact and the downward slide.',
    location: 'Slide along the cheek.',
    movement: 'Move downward along the cheek.',
  },
  ORANGE: {
    default: 'Watch the hand squeeze open and closed at the chin/mouth. Match that location and the squeezing motion.',
    location: 'Keep the action at the chin/mouth.',
    movement: 'Squeeze the hand open and closed, as in the reference.',
  },
  APPLE: {
    default: 'Watch the knuckle twist at the cheek in the reference. Match the cheek contact and the twisting motion.',
    location: 'Keep the action at the cheek.',
    movement: 'Twist at the cheek, as in the reference.',
  },
  MILK: {
    default: 'Watch the hand squeeze open and closed in neutral space like milking. Match the squeezing motion.',
    movement: 'Squeeze the hand open and closed, as in the reference.',
  },
  WATER: {
    default: 'Watch the hand tap at the chin/mouth in the reference. Match the handshape and that location.',
    location: 'Tap at the chin/mouth.',
  },
  CARROT: {
    default: 'Watch the motion near the mouth like biting in the reference. Match the location and the motion rather than holding still.',
    location: 'Keep the action near the mouth.',
  },
  CHOCOLATE: {
    default: 'Watch one hand circle on the back of the other. Match the two-hand setup and the circling motion.',
    movement: 'Circle one hand on the back of the other.',
  },
  PIZZA: {
    default: 'Watch the hand trace a small shape in neutral space. Match the handshape and the path shown in the reference.',
    movement: 'Trace the path shown, do not hold still.',
  },
  ICECREAM: {
    default: 'Watch the motion at the mouth like licking a cone. Match the location and the repeated motion.',
    location: 'Keep the action at the mouth.',
    movement: 'Repeat the licking-cone motion, as in the reference.',
  },
  DRINK: {
    default: 'Watch the curved hand tip up toward the mouth like a cup. Match the cupped handshape and the tipping motion.',
    location: 'Bring the hand to the mouth.',
    movement: 'Tip the cupped hand up like drinking.',
  },
  FOOD: {
    default: 'Watch the fingertips tap at the mouth like eating. Match that location and the tapping motion.',
    location: 'Tap the fingertips at the mouth.',
    movement: 'Bring the fingertips to the mouth, as in the reference.',
  },
  GO: {
    default: 'Watch the hands point and move away from the body. Match the outward direction shown in the reference.',
    movement: 'Move outward/away, as in the reference.',
  },
  GIVE: {
    default: 'Watch the hand move outward from the body toward a receiver. Match the handshape and that forward motion.',
    movement: 'Move the hand outward/away from you.',
  },
  LOOK: {
    default: 'Watch the V-shape near the eyes move outward in the reference. Match the eye start and the forward direction.',
    location: 'Start near the eyes.',
    movement: 'Move the hand outward from the eyes.',
  },
  SEE: {
    default: 'Watch the V-shape near the eyes move outward in the reference. Match the eye start and the forward direction.',
    location: 'Start near the eyes.',
    movement: 'Move outward from the eyes, as in the reference.',
  },
  READ: {
    default: 'Watch the V-shape move down over the flat palm like scanning lines. Match the two-hand setup and the downward motion.',
    movement: 'Move the fingers down over the open palm.',
  },
  LIKE: {
    default: 'Watch the hand start on the chest and draw outward as the fingers close. Match the chest start and that motion.',
    location: 'Start on the chest.',
    movement: 'Pull outward as the fingers draw together.',
  },
  HAVE: {
    default: 'Watch the fingertips come back to the chest in the reference. Match the chest contact at the end.',
    location: 'Bring the fingertips to the chest.',
    movement: 'Move the hands in toward the chest.',
  },
  MAKE: {
    default: 'Watch the two fists stack and twist in the reference. Match the stacked setup and the twisting motion.',
    movement: 'Stack and twist the fists, as in the reference.',
  },
  JUMP: {
    default: 'Watch the fingers stand on the flat palm and hop up. Match the two-hand setup and the upward jump.',
    movement: 'Hop the fingers up off the palm.',
  },
  DANCE: {
    default: 'Watch the V-fingers swing back and forth over the flat palm. Match the two-hand setup and the swinging motion.',
    movement: 'Swing the fingers side to side over the palm.',
  },
  RIDE: {
    default: 'Watch the curved fingers hook onto the other hand and move forward. Match the two-hand link and the forward motion.',
    movement: 'Move the linked hands forward, as in the reference.',
  },
  SLEEP: {
    default: 'Watch the hand pass down over the face as it closes, eyes implied shut. Match the face start and the closing motion.',
    location: 'Start at the face.',
    movement: 'Draw the hand down as the fingers close.',
  },
  TALK: {
    default: 'Watch the fingers move near the mouth in the reference. Match that location and the repeated motion.',
    location: 'Keep the action at the mouth.',
    movement: 'Repeat the small motion, do not hold still.',
  },
  HEAR: {
    default: 'Watch the finger point to the ear in the reference. Match that location.',
    location: 'Point to the ear.',
  },
  FIND: {
    default: 'Watch the fingers pinch and lift upward like picking something up. Match the pinch and the upward lift.',
    movement: 'Pinch and lift upward, as in the reference.',
  },
  HAPPY: {
    default: 'Watch the flat hands brush up the chest repeatedly. Match the chest contact and the upward brushing.',
    location: 'Brush at the chest.',
    movement: 'Brush upward repeatedly, as in the reference.',
  },
  SAD: {
    default: 'Watch the open hands move down in front of the face. Match the face start and the downward motion.',
    location: 'Start in front of the face.',
    movement: 'Move the hands downward, as in the reference.',
  },
  MAD: {
    default: 'Watch the clawed hand pull in front of the face in the reference. Match the handshape and that location.',
    location: 'Keep the hand in front of the face.',
  },
  SICK: {
    default: 'Watch the middle finger touch the forehead in the reference. Match that location.',
    location: 'Touch the forehead.',
  },
  SLEEPY: {
    default: 'Watch the hand droop down over the face/eyes in the reference. Match the face start and the drooping motion.',
    location: 'Start at the face.',
    movement: 'Let the hand droop downward, as in the reference.',
  },
  THIRSTY: {
    default: 'Watch the finger trace down the throat in the reference. Match the throat location and the downward stroke.',
    location: 'Trace down the throat.',
    movement: 'Move the finger downward, as in the reference.',
  },
  PRETTY: {
    default: 'Watch the open hand circle in front of the face in the reference. Match the face location and the circling motion.',
    location: 'Circle in front of the face.',
    movement: 'Circle the hand, as in the reference.',
  },
  CUTE: {
    default: 'Watch the fingers brush down the chin in the reference. Match the chin contact and the downward brush.',
    location: 'Brush at the chin.',
    movement: 'Brush the fingers downward, as in the reference.',
  },
  HOT: {
    default: 'Watch the clawed hand turn away from the mouth quickly. Match the mouth start and the turning-away motion.',
    location: 'Start at the mouth.',
    movement: 'Turn the hand away quickly, as in the reference.',
  },
  DIRTY: {
    default: 'Watch the fingers wiggle under the chin in the reference. Match the under-chin location and the wiggling.',
    location: 'Keep the hand under the chin.',
    movement: 'Wiggle the fingers, as in the reference.',
  },
  FINE: {
    default: 'Watch the thumb tap the chest in the reference. Match the open handshape and the chest contact.',
    location: 'Tap at the chest.',
  },
  NOW: {
    default: 'Watch both hands drop slightly in front of the body. Match the chest-level position and the small downward motion.',
    movement: 'Drop the hands slightly, as in the reference.',
  },
  MORNING: {
    default: 'Watch one forearm rise like the sun over the other arm. Match the two-arm setup and the rising motion.',
    movement: 'Raise the forearm upward, as in the reference.',
  },
  NIGHT: {
    default: 'Watch the curved hand drop over the back of the other hand like a setting sun. Match the two-hand setup.',
    movement: 'Bend the hand down over the other, as in the reference.',
  },
  TOMORROW: {
    default: 'Watch the thumb at the cheek move forward in the reference. Match the cheek start and the forward motion.',
    location: 'Start at the cheek.',
    movement: 'Move the thumb forward, as in the reference.',
  },
  YESTERDAY: {
    default: 'Watch the thumb at the cheek move back toward the ear. Match the cheek start and the backward motion.',
    location: 'Start at the cheek.',
    movement: 'Move the thumb back toward the ear.',
  },
  HOME: {
    default: 'Watch the fingertips touch the cheek in two spots in the reference. Match the cheek location and the motion.',
    location: 'Touch at the cheek.',
  },
  STORE: {
    default: 'Watch both hands flip forward at the wrists in the reference. Match the handshape and the flipping motion.',
    movement: 'Flip the wrists forward, as in the reference.',
  },
  BEDROOM: {
    default: 'Watch the BED cue (head to tilted hand) combined with a room boundary. Match the sequence shown in the reference.',
    movement: 'Match the two-part sequence shown, in order.',
  },
  BATHROOM: {
    default: 'Watch the shaken letter shape in neutral space. Match the handshape, then add the small shake shown.',
    movement: 'Add the small shake, as in the reference.',
  },
  OUTSIDE: {
    default: 'Watch the hand move outward/away in the reference. Match the outward direction and the closing fingers.',
    movement: 'Move outward/away, as in the reference.',
  },
  BED: {
    default: 'Watch the head tilt onto the flat hand like a pillow. Match the head-to-hand contact shown in the reference.',
    location: 'Rest the head on the hand near the cheek.',
  },
  CHAIR: {
    default: 'Watch the curved fingers sit on the other hand like legs on a seat. Match the two-hand setup and the tapping.',
    movement: 'Tap the fingers onto the other hand, as in the reference.',
  },
  TABLE: {
    default: 'Watch one forearm rest flat across the other in the reference. Match the flat stacked-forearm setup.',
    location: 'Rest one forearm across the other.',
  },
  BOOK: {
    default: 'Watch the flat palms open like a book in the reference. Match the two-hand setup and the opening motion.',
    movement: 'Open the palms like a book, as in the reference.',
  },
  PEN: {
    default: 'Watch the hand move as if writing in the reference. Match the handshape and the writing motion.',
    movement: 'Trace a writing motion, as in the reference.',
  },
  SHIRT: {
    default: 'Watch the fingers pinch and tug at the chest/shoulder in the reference. Match that location and the pinch.',
    location: 'Pinch at the chest/shoulder.',
  },
  SHOE: {
    default: 'Watch the two fists tap together in the reference. Match the fist handshape and the tapping motion.',
    movement: 'Tap the fists together, as in the reference.',
  },
  HAT: {
    default: 'Watch the hand pat the top of the head in the reference. Match the head location and the patting motion.',
    location: 'Pat the top of the head.',
    movement: 'Pat the head, as in the reference.',
  },
  TOY: {
    default: 'Watch the shaken letter shapes in neutral space. Match the handshape, then add the small shake shown.',
    movement: 'Add the small shake, as in the reference.',
  },
  EYE: {
    default: 'Watch the finger point to the eye in the reference. Match that location.',
    location: 'Point to the eye.',
  },
  EAR: {
    default: 'Watch the finger point to the ear in the reference. Match that location.',
    location: 'Point to the ear.',
  },
  NOSE: {
    default: 'Watch the finger point to the nose in the reference. Match that location.',
    location: 'Point to the nose.',
  },
  MOUTH: {
    default: 'Watch the finger point around the mouth in the reference. Match that location.',
    location: 'Point around the mouth.',
  },
  HEAD: {
    default: 'Watch the hand touch the head in two spots in the reference. Match the head location and the motion.',
    location: 'Touch the head.',
  },
  HAIR: {
    default: 'Watch the fingers pinch a strand of hair in the reference. Match the pinch and that location.',
    location: 'Pinch at the hair.',
  },
  YES: {
    default: 'Watch the fist nod up and down like a head nodding. Match the fist handshape and the nodding motion.',
    movement: 'Nod the fist up and down, as in the reference.',
  },
  NO: {
    default: 'Watch the fingers snap closed against the thumb in the reference. Match the handshape and the snapping motion.',
    movement: 'Snap the fingers down to the thumb, as in the reference.',
  },
  PLEASE: {
    default: 'Watch the flat hand circle on the chest in the reference. Match the chest contact and the circling motion.',
    location: 'Circle on the chest.',
    movement: 'Circle the flat hand, as in the reference.',
  },
  THANKYOU: {
    default: 'Watch the flat hand start at the chin and move outward. Match the chin start and the forward motion.',
    location: 'Start at the chin.',
    movement: 'Move the hand outward from the chin.',
  },
  WHO: {
    default: 'Watch the action near the mouth/chin in the reference. Match that location and the motion rather than holding still.',
    location: 'Keep the action near the mouth/chin.',
  },
};

/** Lookup a sign's hint copy by gloss (case-insensitive). Null if unauthored. */
export function getSignHint(gloss: string): SignHint | null {
  return SIGN_HINTS[gloss.toUpperCase()] ?? null;
}
