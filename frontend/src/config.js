// Feature flags. The guide pages and all links to them are kept in the
// codebase but hidden from users when this is false — flip to true to
// re-enable the "How it was built" guide throughout the app.
export const GUIDES_ENABLED = false;

// The reading guide for the Super Signals, Best pairs and SUPERHOT panels,
// linked from every world's footer. A PDF this app serves itself
// (public/guides/, copied into the build), so the link needs no outside
// service and no sign-in. Exported from the guide's doc; re-export it there
// and replace the file when the guide changes.
export const READING_GUIDE_URL = '/guides/super-signals-reading-guide.pdf';
