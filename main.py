#!/usr/bin/env python3
import asyncio
import sys
from bot import main

if __name__ == "__main__":
    portfolio = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
    asyncio.run(main(portfolio_usdc=portfolio))
