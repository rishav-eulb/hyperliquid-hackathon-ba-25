// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice ERC-7540 Async Deposit/Redeem interface
interface IERC7540 {
    // Events
    event DepositRequest(
        address indexed controller,
        address indexed owner,
        uint256 indexed requestId,
        address sender,
        uint256 assets
    );

    event RedeemRequest(
        address indexed controller,
        address indexed owner,
        uint256 indexed requestId,
        address sender,
        uint256 shares
    );

    // Deposit flow
    function requestDeposit(
        uint256 assets,
        address controller,
        address owner
    ) external returns (uint256 requestId);

    function pendingDepositRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isPending, uint256 assets);

    function claimableDepositRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isClaimable, uint256 shares);

    function deposit(
        uint256 assets,
        address receiver,
        address controller
    ) external returns (uint256 shares);

    // Redeem flow
    function requestRedeem(
        uint256 shares,
        address controller,
        address owner
    ) external returns (uint256 requestId);

    function pendingRedeemRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isPending, uint256 shares);

    function claimableRedeemRequest(
        uint256 requestId,
        address controller
    ) external view returns (bool isClaimable, uint256 assets);

    function redeem(
        uint256 shares,
        address receiver,
        address controller
    ) external returns (uint256 assets);
}
