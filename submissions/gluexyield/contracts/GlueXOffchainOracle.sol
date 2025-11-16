// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";

import "./interfaces/IPriceOracle.sol";

/**
 * @title GlueXOffchainOracle
 * @notice Price oracle fed by off-chain GlueX /price API
 * @dev Stores prices as 1e18-scaled values representing how much baseAsset
 *      you get for 1 unit (10^decimals) of tokenIn
 */
contract GlueXOffchainOracle is IPriceOracle, Ownable {
    struct PriceData {
        uint256 price;       // price of tokenIn in units of baseAsset, scaled to 1e18
        uint256 lastUpdated; // timestamp
    }

    // mapping[tokenIn][baseAsset] => PriceData
    mapping(address => mapping(address => PriceData)) public prices;

    // max allowed staleness, e.g. 3600 seconds (1 hour)
    uint256 public maxStaleness = 3600;

    event PriceUpdated(
        address indexed tokenIn,
        address indexed baseAsset,
        uint256 price,
        uint256 timestamp
    );

    event MaxStalenessUpdated(uint256 oldValue, uint256 newValue);

    constructor() Ownable() {}

    /// @notice Update price for a token pair
    /// @dev Only owner (or you can change to a "keeper" role if you prefer).
    /// @param tokenIn The token being priced
    /// @param baseAsset The numeraire token
    /// @param price1e18 Price scaled to 1e18 (how much baseAsset for 1 tokenIn)
    function setPrice(
        address tokenIn,
        address baseAsset,
        uint256 price1e18
    ) external onlyOwner {
        require(tokenIn != address(0) && baseAsset != address(0), "Zero address");
        require(price1e18 > 0, "Zero price");

        prices[tokenIn][baseAsset] = PriceData({
            price: price1e18,
            lastUpdated: block.timestamp
        });

        emit PriceUpdated(tokenIn, baseAsset, price1e18, block.timestamp);
    }

    /// @notice Update multiple prices in one transaction
    /// @param tokensIn Array of tokens being priced
    /// @param baseAssets Array of numeraire tokens
    /// @param prices1e18 Array of prices scaled to 1e18
    function setPrices(
        address[] calldata tokensIn,
        address[] calldata baseAssets,
        uint256[] calldata prices1e18
    ) external onlyOwner {
        require(
            tokensIn.length == baseAssets.length && tokensIn.length == prices1e18.length,
            "Length mismatch"
        );

        for (uint256 i = 0; i < tokensIn.length; i++) {
            require(tokensIn[i] != address(0) && baseAssets[i] != address(0), "Zero address");
            require(prices1e18[i] > 0, "Zero price");

            prices[tokensIn[i]][baseAssets[i]] = PriceData({
                price: prices1e18[i],
                lastUpdated: block.timestamp
            });

            emit PriceUpdated(tokensIn[i], baseAssets[i], prices1e18[i], block.timestamp);
        }
    }

    /// @notice Set maximum allowed staleness for prices
    function setMaxStaleness(uint256 newMax) external onlyOwner {
        emit MaxStalenessUpdated(maxStaleness, newMax);
        maxStaleness = newMax;
    }

    /// @inheritdoc IPriceOracle
    function quote(
        address tokenIn,
        address baseAsset,
        uint256 amountIn
    ) external view override returns (uint256 amountBase) {
        // Special case: same token
        if (tokenIn == baseAsset) {
            return amountIn;
        }

        PriceData memory p = prices[tokenIn][baseAsset];
        require(p.price > 0, "No price");
        require(p.lastUpdated + maxStaleness >= block.timestamp, "Price stale");

        if (amountIn == 0) return 0;

        uint8 tokenDecimals = IERC20Metadata(tokenIn).decimals();
        uint8 baseDecimals  = IERC20Metadata(baseAsset).decimals();

        // normalize amountIn to 18 decimals
        uint256 amountIn1e18;
        if (tokenDecimals >= 18) {
            amountIn1e18 = amountIn / 10**(tokenDecimals - 18);
        } else {
            amountIn1e18 = amountIn * 10**(18 - tokenDecimals);
        }

        // value in baseAsset (still as 18-decimal)
        // amountIn1e18 * price1e18 / 1e18
        uint256 value1e18 = (amountIn1e18 * p.price) / 1e18;

        // convert 18-decimal value to baseAsset decimals
        if (baseDecimals >= 18) {
            amountBase = value1e18 * 10**(baseDecimals - 18);
        } else {
            amountBase = value1e18 / 10**(18 - baseDecimals);
        }
    }

    /// @inheritdoc IPriceOracle
    function lastUpdate(
        address tokenIn,
        address baseAsset
    ) external view override returns (uint256) {
        return prices[tokenIn][baseAsset].lastUpdated;
    }

    /// @notice Get price data for a token pair
    function getPriceData(
        address tokenIn,
        address baseAsset
    ) external view returns (uint256 price, uint256 lastUpdated) {
        PriceData memory p = prices[tokenIn][baseAsset];
        return (p.price, p.lastUpdated);
    }
}
