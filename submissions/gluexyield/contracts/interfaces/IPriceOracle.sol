// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Price oracle interface used by VaultManager to value positions in base asset.
interface IPriceOracle {
    /// @notice Return value of `amountIn` of `tokenIn` denominated in `baseAsset`.
    /// @dev MUST revert if the price is stale or unavailable.
    /// @param tokenIn   ERC20 token we are valuing.
    /// @param baseAsset ERC20 token used as numeraire.
    /// @param amountIn  Amount of tokenIn, in its own decimals.
    /// @return amountBase Value denominated in baseAsset (in baseAsset decimals).
    function quote(
        address tokenIn,
        address baseAsset,
        uint256 amountIn
    ) external view returns (uint256 amountBase);

    /// @notice Return last update timestamp for `tokenIn -> baseAsset`.
    function lastUpdate(
        address tokenIn,
        address baseAsset
    ) external view returns (uint256);
}
