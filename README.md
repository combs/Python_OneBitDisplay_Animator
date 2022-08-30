# Python_OneBitDisplay_Animator

This is a Python compressor that accepts GIF files and outputs them to formats usable by the `obdPlayAnimFrame` function in the [OneBitDisplay](https://github.com/bitbank2/OneBitDisplay) Arduino library.

It performs the same function as [oled_animator](https://github.com/bitbank2/oled_animator) but is a reimplementation in Python, avoiding the library licensing issues of the original.

## Example usage

```
$ python3 OBDAnimator.py input.gif output.out --c true --binary true

# Creates output.out.h and output.out
# 
# #include "output.out.h" within your Arduino sketchbook

```

## Tested with

- OneBitDisplay 1.11.0
- SSD1306 128x64 and 64x32
- AVR

## Known issues

- `OneBitDisplay` 2.x does not seem to have a working `obdPlayAnimFrame` as of 8/30/2022. Its example file displays in a garbled fashion. Use version 1.11.0.
- `Python_OneBitDisplay_Animator` does not currently resize, crop, pad, or invert input images. ffmpeg is recommended for this.
- Debug output is not currently suppressable.

## OBDParseOpcodes

It may be helpful to you in debugging to see what opcodes are written by the compressor. You may use `OBDParseOpcodes.py` on a binary-format output file for this.
