# Step 1: Clothing Extraction Instructions

## Your Task
Analyze clothing in images and extract only the essential garment details needed for fashion photography prompts.

## What to Extract FROM INPUT IMAGE

### Garment Types and Details
- Identify each piece of clothing (shirt, dress, pants, jacket, etc.)
- Note specific garment style (button-up, polo, midi dress, skinny jeans, blazer, etc.)
- Record garment construction details (pleated, fitted, oversized, cropped, etc.)

### Colors, Patterns, and Textures
- **Colors:** Primary and accent colors, color combinations
- **Patterns:** Floral, striped, plaid, geometric, solid, etc.
- **Textures:** Cotton, denim, silk, knit, leather, lace, etc.
- **Finishes:** Matte, glossy, distressed, washed, etc.

### Specific Garment Features
- **Necklines:** V-neck, crew neck, scoop neck, off-shoulder, etc.
- **Sleeves:** Long, short, sleeveless, puffed, bell, rolled, etc.
- **Length:** Cropped, regular, long, midi, maxi, mini, etc.
- **Fit:** Fitted, loose, oversized, tailored, relaxed, etc.
- **Details:** Buttons, zippers, pockets, belts, tucks, etc.

### Accessories Worn by Model
- Jewelry (necklaces, earrings, bracelets, rings)
- Bags or purses
- Belts
- Hats or headwear
- Scarves
- Sunglasses
- Watches

## What to COMPLETELY IGNORE

### Visual Elements to Skip
- Background settings or environments
- Model's pose or body position
- Model's facial expression or appearance
- Lighting conditions or mood
- Camera angles or composition
- Any people in the background

### Footwear Exception
- **DO NOT extract footwear from the input image**
- Footwear will be selected separately based on outfit compatibility
- Ignore any shoes, boots, sandals, or barefoot styling in the source image

## Output Format

Provide your analysis in the following structured format:

**Outfit:** "[Complete detailed description of all clothing items with materials, colors, patterns, fit, and styling details]"

**Accessories:** "[Complete detailed description of all accessories including jewelry, bags, hats, belts, etc.]"

## Example Outputs

**Example 1:**
**Outfit:** "Crisp white cotton button-up shirt with classic collar and rolled sleeves tucked into high-waisted medium wash blue denim jeans with straight leg fit"
**Accessories:** "Delicate gold chain necklace and small gold hoop earrings"

**Example 2:**
**Outfit:** "Flowing floral print midi dress in coral and white pattern featuring sweetheart neckline and short puffed sleeves with A-line silhouette in lightweight fabric"
**Accessories:** "Wide-brimmed natural straw hat"

**Example 3:**
**Outfit:** "Oversized cream cable-knit sweater with dropped shoulders and ribbed cuffs worn over black high-waisted leather mini skirt"
**Accessories:** "Layered silver chain necklaces, chunky silver rings, and black leather crossbody bag with gold hardware"

## Quality Check
Before finalizing your extraction, ensure you have:
- ✓ Described every visible garment in detail
- ✓ Captured all colors and patterns accurately  
- ✓ Noted fabric textures and finishes
- ✓ Listed all distinctive features
- ✓ Included every accessory worn by the model
- ✓ Ignored background, lighting, pose, and footwear
- ✓ Used specific, descriptive language rather than generic terms